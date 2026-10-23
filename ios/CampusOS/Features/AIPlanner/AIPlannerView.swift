import SwiftUI

struct AIPlannerView: View {
    @State private var idea = ""
    var body: some View {
        Form {
            Section {
                Label("Campus AI Planner", systemImage: "sparkles")
                    .font(.title2.bold())
                Text("Describe what you want to build. Resource recommendations will be connected to a verified backend later.")
                    .foregroundStyle(.secondary)
            }
            Section("Project idea") {
                TextField("e.g. Build a line-following robot", text: $idea, axis: .vertical)
                    .lineLimit(3...6)
            }
            if !idea.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                Section("Next step") {
                    Text("Idea saved in this screen. AI recommendations aren't enabled yet.")
                }
            }
        }
        .navigationTitle("AI Planner")
    }
}
