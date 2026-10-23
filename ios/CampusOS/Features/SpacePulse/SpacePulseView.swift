import SwiftUI
struct SpacePulseView: View {
    var body: some View {
        ContentUnavailableView("Campus Space Management", systemImage: "building.2.fill",
            description: Text("Room reservations and real occupancy integration are planned."))
        .navigationTitle("SpacePulse")
    }
}
