import SwiftUI

struct LabBookingView: View {
    let lab: Lab
    @EnvironmentObject private var bookingStore: BookingStore
    @State private var selectedDate = Date().addingTimeInterval(3600)
    @State private var duration = 60
    @State private var alertText = ""
    @State private var showingAlert = false
    @State private var didSucceed = false

    var body: some View {
        Form {
            Section("Reservation details") {
                LabeledContent("Laboratory", value: lab.name)
                DatePicker("Start time", selection: $selectedDate, in: Date()...,
                           displayedComponents: [.date, .hourAndMinute])
                Picker("Duration", selection: $duration) {
                    Text("30 min").tag(30)
                    Text("1 hour").tag(60)
                    Text("2 hours").tag(120)
                }
            }
            Section {
                Button("Confirm Reservation") {
                    do {
                        try bookingStore.reserve(lab: lab, start: selectedDate,
                                                  durationMinutes: duration)
                        alertText = "Booking saved. Open the Bookings tab to view it."
                        didSucceed = true
                    } catch {
                        alertText = error.localizedDescription
                        didSucceed = false
                    }
                    showingAlert = true
                }
                .frame(maxWidth: .infinity)
            } footer: {
                Text("Demo only: bookings are stored on this device, not shared with other students.")
            }
        }
        .navigationTitle("Book Lab")
        .alert(didSucceed ? "Reservation Confirmed" : "Booking Failed",
               isPresented: $showingAlert) {
            Button("OK", role: .cancel) {}
        } message: {
            Text(alertText)
        }
    }
}
