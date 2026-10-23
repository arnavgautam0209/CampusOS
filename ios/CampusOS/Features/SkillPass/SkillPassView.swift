import SwiftUI

struct SkillPassView: View {
    var body: some View {
        List {
            Section("Example training records") {
                HStack {
                    Label("Basic Electronics", systemImage: "checkmark.seal.fill")
                    Spacer()
                    StatusBadge(text: "Approved", color: .green)
                }
                HStack {
                    Label("Soldering Station", systemImage: "hand.raised")
                    Spacer()
                    StatusBadge(text: "Approval needed", color: .orange)
                }
            }
            Section {
                Text("Real training certifications must be issued by authorized faculty. These entries are illustrative.")
                    .foregroundStyle(.secondary)
            }
        }
        .navigationTitle("SkillPass")
    }
}
