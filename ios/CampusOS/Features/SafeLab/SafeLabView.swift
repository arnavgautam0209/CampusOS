import SwiftUI

struct SafeLabView: View {
    var body: some View {
        List {
            Section("Environment — demo readings") {
                Label("Temperature: 24 °C", systemImage: "thermometer.medium")
                Label("Humidity: 48%", systemImage: "humidity")
                Label("Sensor: Not connected", systemImage: "wifi.slash")
            }
            Section("Safety notices") {
                Label("No live safety telemetry is available.", systemImage: "info.circle")
                Text("ESP32 sensor readings and faculty incident reports will appear here after backend integration.")
                    .foregroundStyle(.secondary)
            }
        }
        .navigationTitle("SafeLab")
    }
}
