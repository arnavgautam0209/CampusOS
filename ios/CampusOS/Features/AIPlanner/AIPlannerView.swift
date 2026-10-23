import SwiftUI

struct AIPlannerView: View {
    @State private var projectIdea = ""

    var body: some View {
        Form {
            Section {
                Label("Campus AI Planner", systemImage: "sparkles")
                    .font(.headline)
                Text("Tell CampusOS what you want to build.")
                    .foregroundStyle(.secondary)
                TextField("e.g. Build a line-following robot", text: $projectIdea,
                          axis: .vertical)
                    .lineLimit(3...6)
            }
            Section("Planning status") {
                if projectIdea.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                    Text("Enter an idea to begin.")
                        .foregroundStyle(.secondary)
                } else {
                    Text("Idea captured: \(projectIdea)")
                    Text("AI recommendations will appear once the backend is integrated.")
                        .font(.caption).foregroundStyle(.secondary)
                }
            }
        }
        .navigationTitle("AI Planner")
    }
}
