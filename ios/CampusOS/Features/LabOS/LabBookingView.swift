import SwiftUI

struct LabBookingView: View {
    let lab: Lab
    @EnvironmentObject private var bookingStore: BookingStore
    @EnvironmentObject private var auth: AuthManager
    @State private var selectedDate = Date().addingTimeInterval(3600)
    @State private var duration = 60
    @State private var purpose = ""
    @State private var isSubmitting = false
    @State private var showingSignIn = false
    @State private var alertText = ""
    @State private var showingAlert = false
    @State private var alertTitle = ""

    /// Faculty book directly; students' bookings for approval labs become requests.
    private var needsApproval: Bool { lab.requiresApproval && auth.currentUser?.role.isStaff != true }

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
                TextField(needsApproval ? "What will you work on? (shown to faculty)" : "Purpose (optional)",
                          text: $purpose, axis: .vertical)
                    .lineLimit(1...3)
            }
            if auth.isSignedIn {
                Section {
                    Button {
                        Task { await reserve() }
                    } label: {
                        HStack {
                            Spacer()
                            if isSubmitting {
                                ProgressView()
                            } else {
                                Text(needsApproval ? "Send Request" : "Confirm Reservation")
                            }
                            Spacer()
                        }
                    }
                    .disabled(isSubmitting)
                } footer: {
                    Text(needsApproval
                         ? "Faculty approve bookings for this lab. The time is held for you while they decide."
                         : "The CampusOS server checks this time against every student's bookings.")
                }
            } else {
                Section {
                    Button("Sign In to Reserve") { showingSignIn = true }
                        .frame(maxWidth: .infinity)
                } footer: {
                    Text("You need to sign in so the lab knows who booked it.")
                }
            }
        }
        .navigationTitle("Book Lab")
        .sheet(isPresented: $showingSignIn) {
            NavigationStack { SignInView(showsCancel: true) }
        }
        .alert(alertTitle,
               isPresented: $showingAlert) {
            Button("OK", role: .cancel) {}
        } message: {
            Text(alertText)
        }
    }

    private func reserve() async {
        isSubmitting = true
        defer { isSubmitting = false }
        do {
            let booking = try await bookingStore.reserve(lab: lab, start: selectedDate, durationMinutes: duration,
                                                         purpose: purpose)
            if booking.status == .pending {
                alertTitle = "Request Sent"
                alertText = "A faculty member will review it. The time is held for you; check the Bookings tab for the decision."
            } else {
                alertTitle = "Reservation Confirmed"
                alertText = "Booking saved. Open the Bookings tab to view it."
            }
        } catch {
            alertTitle = "Booking Failed"
            alertText = error.localizedDescription
        }
        showingAlert = true
    }
}
