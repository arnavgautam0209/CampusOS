import SwiftUI

struct SpacePulseView: View {
    var body: some View {
        List {
            Section("Rooms — sample directory") {
                Label("Innovation Centre · Study Room", systemImage: "building.2")
                Label("Block A · Seminar Hall", systemImage: "person.3")
                Label("Block C · Meeting Room", systemImage: "door.left.hand.closed")
            }
            Section {
                Text("Room availability and sensor-based occupancy are not connected yet.")
                    .foregroundStyle(.secondary)
            }
        }
        .navigationTitle("SpacePulse")
    }
}
