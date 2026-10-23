import SwiftUI

struct LabBookingView: View {
    let lab: Lab
    @EnvironmentObject private var store: BookingStore
    @State private var date = Date().addingTimeInterval(7200)
    @State private var message = ""
    @State private var showingAlert = false

    var body: some View {
        Form {
            Section("Laboratory") {
                Text(lab.name)
                Text("Duration: 60 minutes").foregroundStyle(.secondary)
            }
            Section("Time") {
                DatePicker("Start", selection: $date, in: Date()...,
                           displayedComponents: [.date, .hourAndMinute])
            }
            Section {
                Button("Confirm Reservation") {
                    do {
                        try store.reserve(lab, at: date)
                        message = "Reserved! Open the Bookings tab to view it."
                    } catch {
                        message = error.localizedDescription
                    }
                    showingAlert = true
                }
                .disabled(!lab.isOpenForBooking)
            }
        }
        .navigationTitle("Reserve Lab")
        .alert("Reservation", isPresented: $showingAlert) {
            Button("OK", role: .cancel) {}
        } message: { Text(message) }
    }
}
