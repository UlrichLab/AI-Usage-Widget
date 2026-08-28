import SwiftUI
import WidgetKit

private let endpoint = URL(string: "http://127.0.0.1:38471/usage")!

struct UsageSnapshot: Codable {
    let updated: String
    let claudeRemaining: Double?
    let codexRemaining: Double?
    let cursorRemaining: Double?
}

struct UsageEntry: TimelineEntry {
    let date: Date
    let snapshot: UsageSnapshot?
}

struct UsageProvider: TimelineProvider {
    func placeholder(in context: Context) -> UsageEntry {
        UsageEntry(date: Date(), snapshot: UsageSnapshot(
            updated: "", claudeRemaining: 72, codexRemaining: 94, cursorRemaining: 37))
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
            completion(Timeline(entries: [entry], policy: .after(Date().addingTimeInterval(300))))
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

struct UsageBar: View {
    let title: String
    let remaining: Double?

    private var value: Double { min(100, max(0, remaining ?? 0)) }
    private var color: Color {
        value >= 30 ? .green : (value >= 10 ? .orange : .red)
    }

    var body: some View {
        VStack(spacing: 4) {
            HStack {
                Text(title).font(.headline).fontWeight(.bold)
                Spacer()
                Text(remaining.map { "\(Int($0.rounded())) % frei" } ?? "—")
                    .font(.subheadline).fontWeight(.bold)
            }
            GeometryReader { geometry in
                ZStack(alignment: .leading) {
                    Capsule().fill(.secondary.opacity(0.22))
                    Capsule().fill(color).frame(width: geometry.size.width * value / 100)
                }
            }
            .frame(height: 7)
        }
    }
}

struct AIUsageWidgetView: View {
    let entry: UsageEntry

    var body: some View {
        VStack(alignment: .leading, spacing: 11) {
            if let snapshot = entry.snapshot {
                UsageBar(title: "Claude", remaining: snapshot.claudeRemaining)
                UsageBar(title: "ChatGPT", remaining: snapshot.codexRemaining)
                UsageBar(title: "Cursor", remaining: snapshot.cursorRemaining)
            } else {
                Spacer()
                Text("App öffnen, um Usage-Daten zu laden")
                    .font(.caption).foregroundStyle(.secondary)
                Spacer()
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
        .description("Zeigt die verbleibende Nutzung von Claude, Codex und Cursor.")
        .supportedFamilies([.systemSmall, .systemMedium])
    }
}

@main
struct AIUsageWidgetBundle: WidgetBundle {
    var body: some Widget {
        AIUsageWidget()
    }
}
