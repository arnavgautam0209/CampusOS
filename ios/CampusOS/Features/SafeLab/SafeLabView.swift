import SwiftUI
struct SafeLabView: View {
    var body: some View {
        ContentUnavailableView("Safety & Monitoring", systemImage: "shield.lefthalf.filled",
            description: Text("Environmental readings and incident reporting will connect to sensors later."))
        .navigationTitle("SafeLab")
    }
}
