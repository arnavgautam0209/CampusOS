import SwiftUI

struct ProxyGuardView: View {
    var body: some View {
        List {
            Section("Attendance verification steps") {
                Label("1. NFC credential scanned", systemImage: "creditcard")
                Label("2. Student confirmation", systemImage: "iphone.gen3")
                Label("3. Faculty review when required", systemImage: "person.crop.rectangle")
            }
            Section("Current state") {
                StatusBadge(text: "No live terminal connected", color: .orange)
                Text("Attendance is not being recorded. NFC UID alone does not prove student identity.")
                    .foregroundStyle(.secondary)
            }
        }
        .navigationTitle("ProxyGuard")
    }
}
