"""Provider-neutral usage-window normalization.

This module only receives decoded, non-secret provider responses.  It never
reads, refreshes, writes, or logs credentials.
"""

import re
import unicodedata


WINDOW_PRIORITY = {
    "session": 10,
    "daily": 20,
    "weekly": 30,
    "model": 40,
    "monthly": 50,
    "other": 99,
}


def number(value):
    try:
        parsed = float(value)
        return parsed if parsed == parsed and parsed not in (float("inf"), float("-inf")) else None
    except (TypeError, ValueError):
        return None


def percent(value):
    parsed = number(value)
    return None if parsed is None else max(0.0, min(100.0, parsed))


def slug(value):
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def display_name(value):
    text = str(value or "").replace("_", " ").replace("-", " ").strip()
    return " ".join(word.upper() if word.lower() in {"api", "oauth", "gpt"} else word.capitalize()
                    for word in text.split())


def classify_duration(seconds):
    seconds = number(seconds)
    if seconds is None or seconds <= 0:
        return "other"
    if seconds <= 12 * 3600:
        return "session"
    if seconds <= 2 * 86400:
        return "daily"
    if seconds <= 14 * 86400:
        return "weekly"
    if seconds >= 28 * 86400:
        return "monthly"
    return "other"


def duration_label(seconds, fallback="Limit"):
    seconds = number(seconds)
    if seconds is None or seconds <= 0:
        return fallback
    rounded = int(round(seconds))
    if rounded == 18000:
        return "5 hours"
    if rounded == 604800:
        return "Weekly"
    if rounded % 86400 == 0:
        days = rounded // 86400
        if days == 1:
            return "Daily"
        if 28 <= days <= 31:
            return "Monthly"
        return f"{days} days"
    if rounded % 3600 == 0:
        hours = rounded // 3600
        return f"{hours} hours"
    minutes = max(1, rounded // 60)
    return f"{minutes} minutes"


def make_window(window_id, label, window_type, used_percent, resets_at=None,
                duration_seconds=None, model=None, scope=None, **metadata):
    used = percent(used_percent)
    if used is None:
        return None
    result = {
        "id": window_id,
        "label": label,
        "type": window_type if window_type in WINDOW_PRIORITY else "other",
        "used_percent": used,
        "resets_at": resets_at,
    }
    if duration_seconds is not None:
        result["duration_seconds"] = number(duration_seconds)
    if model:
        result["model"] = model
    if scope:
        result["scope"] = scope
    result.update({key: value for key, value in metadata.items() if value is not None})
    return result


def sort_windows(windows):
    indexed = list(enumerate(window for window in windows if isinstance(window, dict)))
    indexed.sort(key=lambda item: (WINDOW_PRIORITY.get(item[1].get("type"), 99), item[0]))
    return [window for _, window in indexed]


def provider_result(windows, source, plan=None, **metadata):
    windows = sort_windows(windows)
    if not windows:
        return {"status": "error", "message": "No quota data", "windows": [], "source": source}
    first = tightest_window(windows) or windows[0]
    result = {
        "status": "ok",
        "windows": windows,
        "source": source,
        # Compatibility for older callers and the tray summary.
        "label": first["label"],
        "used": first["used_percent"],
        "reset": first.get("resets_at"),
    }
    if plan:
        result["plan"] = plan
    result.update({key: value for key, value in metadata.items() if value is not None})
    return result


def tightest_window(windows):
    valid = [window for window in windows or [] if percent(window.get("used_percent")) is not None]
    return max(valid, key=lambda window: window["used_percent"]) if valid else None


def _oauth_window(data, key, window_id, label, window_type, model=None):
    raw = data.get(key)
    if not isinstance(raw, dict):
        return None
    return make_window(
        window_id,
        label,
        window_type,
        raw.get("utilization"),
        raw.get("resets_at"),
        604800 if key.startswith("seven_day") else 18000 if key == "five_hour" else None,
        model=model,
        scope=key,
    )


def _scope_model(limit):
    scope = limit.get("scope")
    if isinstance(scope, str):
        name = scope.strip()
        return (name or None), (display_name(name) or None)
    model = scope.get("model") if isinstance(scope, dict) else None
    if not isinstance(model, dict):
        return None, None
    model_id = str(model.get("id") or "").strip() or None
    model_name = str(model.get("display_name") or "").strip() or None
    return model_id, model_name


def normalize_claude_usage(data):
    """Map every usable Claude OAuth quota bucket to a generic window."""
    if not isinstance(data, dict):
        return provider_result([], "oauth")

    windows = []
    fixed = [
        ("five_hour", "claude-session-5h", "5 hours", "session", None),
        ("seven_day", "claude-weekly", "Weekly", "weekly", None),
        ("seven_day_sonnet", "claude-weekly-sonnet", "Sonnet · Weekly", "model", "Sonnet"),
        ("seven_day_opus", "claude-weekly-opus", "Opus · Weekly", "model", "Opus"),
    ]
    consumed_keys = {item[0] for item in fixed}
    for key, window_id, label, window_type, model in fixed:
        window = _oauth_window(data, key, window_id, label, window_type, model)
        if window:
            windows.append(window)

    # Anthropic has used several aliases for the same Routines/Cowork lane.
    routines_keys = (
        "seven_day_routines", "seven_day_claude_routines", "claude_routines",
        "routines", "routine", "seven_day_cowork", "cowork",
    )
    consumed_keys.update(routines_keys)
    for key in routines_keys:
        window = _oauth_window(data, key, "claude-routines", "Daily Routines", "model")
        if window:
            windows.append(window)
            break

    seen_ids = {window["id"] for window in windows}
    for limit in data.get("limits") or []:
        if not isinstance(limit, dict):
            continue
        kind = str(limit.get("kind") or limit.get("type") or "").strip().lower()
        group = str(limit.get("group") or "").strip().lower()
        model_id, model_name = _scope_model(limit)
        if kind == "weekly_scoped" and group == "weekly":
            if not model_name:
                continue
            identity = model_id or model_name
            identity_slug = slug(identity)
            if slug(model_name) == "all-models" or identity_slug == "all-models" or identity_slug.endswith("-all-models"):
                continue
            window_id = f"claude-weekly-scoped-{identity_slug}"
            window = make_window(window_id, f"{model_name} · Weekly", "model",
                                 limit.get("percent", limit.get("utilization")), limit.get("resets_at"), 604800,
                                 model=model_name, scope=identity)
        elif kind in {"session", "weekly_all"}:
            # These duplicate the top-level primary lanes when both forms are present.
            continue
        else:
            identity = model_id or model_name or kind or group
            if not identity:
                continue
            window_id = f"claude-limit-{slug(identity)}"
            window_type = "monthly" if group == "monthly" else "daily" if group == "daily" else "weekly" if group == "weekly" else "other"
            label = display_name(model_name or kind or group)
            if window_type == "weekly" and model_name:
                label = f"{model_name} · Weekly"
            window = make_window(window_id, label or "Claude limit", window_type,
                                 limit.get("percent", limit.get("utilization")), limit.get("resets_at"),
                                 model=model_name, scope=identity)
        if window and window["id"] not in seen_ids:
            windows.append(window)
            seen_ids.add(window["id"])

    ignored = {"seven_day_design", "seven_day_omelette", "spend", "extra_usage", "limits"}
    for key, raw in data.items():
        if key in consumed_keys or key in ignored or not isinstance(raw, dict):
            continue
        utilization = number(raw.get("utilization"))
        if utilization is None:
            continue
        # Claude sometimes exposes opaque internal feature codenames (for example
        # `nimbus_quill`) as an inactive 0% object. Without a reset, lock reason,
        # or monetary limit, these are not meaningful user-facing usage lanes.
        if utilization == 0 and not raw.get("resets_at") and not raw.get("locked_reason") \
                and all(number(raw.get(key)) is None for key in
                        ("limit_dollars","used_dollars","remaining_dollars")):
            continue
        window_id = f"claude-{slug(key)}"
        if window_id in seen_ids:
            continue
        inferred_type = "weekly" if key.startswith("seven_day") else "daily" if "daily" in key else "other"
        label = display_name(key.removeprefix("seven_day_"))
        if inferred_type == "weekly":
            label = f"{label} · Weekly" if label else "Weekly"
        window = make_window(window_id, label or "Claude limit", inferred_type,
                             utilization, raw.get("resets_at"),
                             604800 if inferred_type == "weekly" else None, scope=key)
        if window:
            windows.append(window)
            seen_ids.add(window_id)

    spend = data.get("spend") if isinstance(data.get("spend"), dict) else {}
    extra = data.get("extra_usage") if isinstance(data.get("extra_usage"), dict) else {}
    if extra.get("is_enabled") is not False:
        used_percent = spend.get("percent")
        if used_percent is None:
            used_percent = extra.get("utilization")
        used_credits = extra.get("used_credits")
        monthly_limit = extra.get("monthly_limit")
        if used_percent is None and number(used_credits) is not None and number(monthly_limit):
            used_percent = number(used_credits) / number(monthly_limit) * 100
        spend_used = spend.get("used") if isinstance(spend.get("used"), dict) else {}
        spend_limit = spend.get("limit") if isinstance(spend.get("limit"), dict) else {}
        window = make_window(
            "claude-extra-usage", "Extra Usage", "monthly", used_percent,
            extra.get("resets_at") or spend.get("resets_at"),
            used_minor=spend_used.get("amount_minor", used_credits),
            limit_minor=spend_limit.get("amount_minor", monthly_limit),
            exponent=spend_used.get("exponent", spend_limit.get("exponent", 2)),
            currency=extra.get("currency") or "USD",
        )
        if window:
            windows.append(window)

    return provider_result(windows, "oauth")


def normalize_claude_desktop(values):
    """Map all non-sensitive Claude Desktop cache lanes, not just the maximum."""
    if not isinstance(values, dict):
        return provider_result([], "claude-desktop")
    definitions = {
        "fh": ("claude-session-5h", "5 hours", "session", None),
        "sd": ("claude-weekly", "Weekly", "weekly", None),
        "sn": ("claude-weekly-sonnet", "Sonnet · Weekly", "model", "Sonnet"),
        "so": ("claude-weekly-opus", "Opus · Weekly", "model", "Opus"),
        "oa": ("claude-weekly-oauth", "OAuth Apps · Weekly", "model", "OAuth Apps"),
        "cw": ("claude-routines", "Daily Routines", "model", None),
        "om": ("claude-weekly-other", "Claude · Weekly", "model", "Claude"),
        "op": ("claude-promotion", "Claude Promotion", "other", None),
        "xu": ("claude-extra-usage", "Extra Usage", "monthly", None),
    }
    windows = []
    for key, value in values.items():
        window_id, label, window_type, model = definitions.get(
            key, (f"claude-desktop-{slug(key)}", display_name(key) or "Claude limit", "other", None))
        window = make_window(window_id, label, window_type, value, model=model, scope=key)
        if window:
            windows.append(window)
    return provider_result(windows, "claude-desktop")


def _codex_window(raw, window_id, label_prefix=None, fallback="Limit", model=None, scope=None):
    if not isinstance(raw, dict):
        return None
    seconds = raw.get("limit_window_seconds")
    label = duration_label(seconds, fallback)
    if label_prefix:
        label = f"{label_prefix} · {label}"
    window_type = "model" if model else classify_duration(seconds)
    return make_window(window_id, label, window_type, raw.get("used_percent"),
                       raw.get("reset_at"), seconds, model=model, scope=scope)


def normalize_codex_usage(data):
    """Map Codex core and model-specific rate-limit windows."""
    if not isinstance(data, dict):
        return provider_result([], "oauth")
    windows = []
    seen_ids = set()
    rate_limit = data.get("rate_limit")
    if isinstance(rate_limit, dict):
        ordered_keys = ["primary_window", "secondary_window"]
        ordered_keys.extend(key for key in rate_limit if key not in ordered_keys and "window" in key)
        for key in ordered_keys:
            window = _codex_window(rate_limit.get(key), f"codex-{slug(key)}", fallback=display_name(key))
            if window and window["id"] not in seen_ids:
                windows.append(window)
                seen_ids.add(window["id"])

    for entry in data.get("additional_rate_limits") or []:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("limit_name") or entry.get("metered_feature") or "").strip()
        identity = str(entry.get("metered_feature") or name).strip()
        nested = entry.get("rate_limit")
        if not name or not identity or not isinstance(nested, dict):
            continue
        keys = ["primary_window", "secondary_window"]
        keys.extend(key for key in nested if key not in keys and "window" in key)
        for key in keys:
            raw = nested.get(key)
            seconds = raw.get("limit_window_seconds") if isinstance(raw, dict) else None
            duration_identity = slug(duration_label(seconds, key))
            window_id = f"codex-{slug(identity)}-{duration_identity}"
            window = _codex_window(raw, window_id, name, model=name, scope=identity)
            if window and window_id not in seen_ids:
                windows.append(window)
                seen_ids.add(window_id)

    return provider_result(windows, "oauth", plan=data.get("plan_type"))
