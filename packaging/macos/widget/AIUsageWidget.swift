import SwiftUI
import WidgetKit

private let endpoint = URL(string: "http://127.0.0.1:38471/usage")!

struct WidgetUsageWindow: Codable, Identifiable {
    let id: String
    let label: String
    let usedPercent: Double
    let resetsAt: String?
    let type: String

    private enum CodingKeys: String, CodingKey {
        case id, label, usedPercent, resetsAt, type
    }

    init(id: String, label: String, usedPercent: Double, resetsAt: String?, type: String) {
        self.id = id
        self.label = label
        self.usedPercent = usedPercent
        self.resetsAt = resetsAt
        self.type = type
    }

    init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        id = try values.decode(String.self, forKey: .id)
        label = try values.decode(String.self, forKey: .label)
        usedPercent = try values.decode(Double.self, forKey: .usedPercent)
        type = try values.decode(String.self, forKey: .type)
        if let text = try? values.decode(String.self, forKey: .resetsAt) {
            resetsAt = text
        } else if let timestamp = try? values.decode(Double.self, forKey: .resetsAt) {
            resetsAt = String(timestamp)
        } else {
            resetsAt = nil
        }
    }

    var remaining: Double { min(100, max(0, 100 - usedPercent)) }
}

struct WidgetProviderUsage: Codable, Identifiable {
    let id: String
    let title: String
    let windows: [WidgetUsageWindow]

    var tightest: WidgetUsageWindow? {
        windows.max { $0.usedPercent < $1.usedPercent }
    }
}

struct UsageSnapshot: Codable {
    let updated: String
    let claudeRemaining: Double?
    let codexRemaining: Double?
    let cursorRemaining: Double?
    let providers: [WidgetProviderUsage]?
}

struct UsageEntry: TimelineEntry {
    let date: Date
    let snapshot: UsageSnapshot?
}

struct UsageProvider: TimelineProvider {
    func placeholder(in context: Context) -> UsageEntry {
        UsageEntry(date: Date(), snapshot: UsageSnapshot(
            updated: "", claudeRemaining: 72, codexRemaining: 94, cursorRemaining: 37,
            providers: [
                WidgetProviderUsage(id: "claude", title: "Claude", windows: [
                    WidgetUsageWindow(id: "claude-session", label: "5 hours", usedPercent: 28, resetsAt: nil, type: "session"),
                    WidgetUsageWindow(id: "claude-week", label: "Weekly", usedPercent: 22, resetsAt: nil, type: "weekly")
                ]),
                WidgetProviderUsage(id: "codex", title: "ChatGPT", windows: [
                    WidgetUsageWindow(id: "codex-session", label: "5 hours", usedPercent: 6, resetsAt: nil, type: "session"),
                    WidgetUsageWindow(id: "codex-week", label: "Weekly", usedPercent: 20, resetsAt: nil, type: "weekly")
                ]),
                WidgetProviderUsage(id: "cursor", title: "Cursor", windows: [
                    WidgetUsageWindow(id: "cursor-models", label: "Cursor Models", usedPercent: 5, resetsAt: nil, type: "model")
                ])
            ]))
    }

    func getSnapshot(in context: Context, completion: @escaping (UsageEntry) -> Void) {
        if context.isPreview {
            completion(placeholder(in: context))
            return
        }
        load(completion: completion)
    }

    func getTimeline(in context: Context, completion: @escaping (Timeline<UsageEntry>) -> Void) {
        load { entry in
            // At login WidgetKit can run a fraction of a second before the app's
            // local server is listening. Retry an empty startup snapshot quickly;
            // successful snapshots keep the normal five-minute refresh interval.
            let refreshInterval: TimeInterval = entry.snapshot == nil ? 15 : 300
            completion(Timeline(entries: [entry],
                                policy: .after(Date().addingTimeInterval(refreshInterval))))
        }
    }

    private func load(completion: @escaping (UsageEntry) -> Void) {
        var request = URLRequest(url: endpoint)
        request.timeoutInterval = 3
        URLSession.shared.dataTask(with: request) { data, _, _ in
            let snapshot = data.flatMap { try? JSONDecoder().decode(UsageSnapshot.self, from: $0) }
            completion(UsageEntry(date: Date(), snapshot: snapshot))
        }.resume()
    }
}

private func usageColor(_ remaining: Double) -> Color {
    remaining >= 30 ? .green : (remaining >= 10 ? .orange : .red)
}

struct UsageBar: View {
    let title: String
    let remaining: Double?

    private var value: Double { min(100, max(0, remaining ?? 0)) }

    var body: some View {
        VStack(spacing: 4) {
            HStack {
                Text(title).font(.headline).fontWeight(.bold).lineLimit(1)
                Spacer()
                Text(remaining.map { "\(Int($0.rounded())) % free" } ?? "—")
                    .font(.headline).fontWeight(.bold)
            }
            GeometryReader { geometry in
                ZStack(alignment: .leading) {
                    Capsule().fill(.secondary.opacity(0.22))
                    Capsule().fill(usageColor(value)).frame(width: geometry.size.width * value / 100)
                }
            }
            .frame(height: 7)
        }
    }
}

struct DynamicUsageRow: View {
    let provider: String
    let window: WidgetUsageWindow
    let showReset: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack(spacing: 4) {
                Text("\(provider) · \(window.label)")
                    .font(.caption).fontWeight(.semibold).lineLimit(1)
                Spacer(minLength: 4)
                Text("\(Int(window.remaining.rounded())) % free")
                    .font(.subheadline).fontWeight(.bold).lineLimit(1)
            }
            GeometryReader { geometry in
                ZStack(alignment: .leading) {
                    Capsule().fill(.secondary.opacity(0.22))
                    Capsule().fill(usageColor(window.remaining))
                        .frame(width: geometry.size.width * window.remaining / 100)
                }
            }
            .frame(height: 5)
            if showReset, let reset = resetText(window.resetsAt) {
                Text(reset).font(.caption2).foregroundStyle(.secondary).lineLimit(1)
            }
        }
    }

    private func resetText(_ raw: String?) -> String? {
        guard let raw, !raw.isEmpty else { return nil }
        let date: Date?
        if let timestamp = Double(raw) {
            date = Date(timeIntervalSince1970: timestamp)
        } else {
            let formatter = ISO8601DateFormatter()
            formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
            date = formatter.date(from: raw) ?? ISO8601DateFormatter().date(from: raw)
        }
        guard let date else { return nil }
        let formatter = RelativeDateTimeFormatter()
        formatter.unitsStyle = .abbreviated
        return "Reset \(formatter.localizedString(for: date, relativeTo: Date()))"
    }
}

private struct DisplayWindow: Identifiable {
    let id: String
    let provider: String
    let window: WidgetUsageWindow
}

struct AIUsageWidgetView: View {
    @Environment(\.widgetFamily) private var family
    let entry: UsageEntry

    private func legacyProviders(_ snapshot: UsageSnapshot) -> [WidgetProviderUsage] {
        let values: [(String, String, Double?)] = [
            ("claude", "Claude", snapshot.claudeRemaining),
            ("codex", "ChatGPT", snapshot.codexRemaining),
            ("cursor", "Cursor", snapshot.cursorRemaining)
        ]
        return values.compactMap { item in
            let (id, title, remaining) = item
            guard let remaining else { return nil }
            return WidgetProviderUsage(id: id, title: title, windows: [
                WidgetUsageWindow(id: "\(id)-summary", label: title,
                                  usedPercent: 100 - remaining, resetsAt: nil, type: "other")
            ])
        }
    }

    private func providers(_ snapshot: UsageSnapshot) -> [WidgetProviderUsage] {
        let dynamic = snapshot.providers?.filter { !$0.windows.isEmpty } ?? []
        return dynamic.isEmpty ? legacyProviders(snapshot) : dynamic
    }

    private func windows(_ providers: [WidgetProviderUsage]) -> [DisplayWindow] {
        providers.flatMap { provider in
            provider.windows.map {
                DisplayWindow(id: "\(provider.id)-\($0.id)", provider: provider.title, window: $0)
            }
        }
    }

    var body: some View {
        Group {
            if let snapshot = entry.snapshot {
                let available = providers(snapshot)
                if family == .systemSmall {
                    VStack(alignment: .leading, spacing: 9) {
                        ForEach(available) { provider in
                            UsageBar(title: provider.title, remaining: provider.tightest?.remaining)
                        }
                    }
                } else {
                    let allWindows = windows(available)
                    let maximum = family == .systemLarge ? 14 : 7
                    let visible = Array(allWindows.prefix(maximum))
                    VStack(alignment: .leading, spacing: family == .systemLarge ? 7 : 5) {
                        ForEach(visible) { item in
                            DynamicUsageRow(provider: item.provider, window: item.window,
                                            showReset: family == .systemLarge)
                        }
                        if allWindows.count > maximum {
                            Text("+ \(allWindows.count - maximum) more limits")
                                .font(.caption2).foregroundStyle(.secondary)
                        }
                    }
                }
            } else {
                VStack {
                    Spacer()
                    Text("Open the app to load usage data")
                        .font(.caption).foregroundStyle(.secondary)
                    Spacer()
                }
            }
        }
        .padding()
        .containerBackground(for: .widget) { Color(nsColor: .windowBackgroundColor) }
    }
}

struct AIUsageWidget: Widget {
    let kind = "AIUsageWidget"

    var body: some WidgetConfiguration {
        StaticConfiguration(kind: kind, provider: UsageProvider()) { entry in
            AIUsageWidgetView(entry: entry)
        }
        .configurationDisplayName("AI Usage")
        .description("Shows dynamic usage windows from Claude, ChatGPT, and Cursor.")
        .supportedFamilies([.systemSmall, .systemMedium, .systemLarge])
    }
}

@main
struct AIUsageWidgetBundle: WidgetBundle {
    var body: some Widget {
        AIUsageWidget()
    }
}
