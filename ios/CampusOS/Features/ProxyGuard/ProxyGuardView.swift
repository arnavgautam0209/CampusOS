import SwiftUI
struct ProxyGuardView: View {
    var body: some View {
        ContentUnavailableView("Attendance Integrity", systemImage: "person.crop.rectangle.stack",
            description: Text("NFC verification and faculty review will be added after backend integration."))
        .navigationTitle("ProxyGuard")
    }
}
