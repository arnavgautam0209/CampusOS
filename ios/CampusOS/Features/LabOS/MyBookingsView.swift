import SwiftUI

struct MyBookingsView: View {
    @EnvironmentObject private var store: BookingStore
    var body: some View {
        Group {
            if store.bookings.isEmpty {
                ContentUnavailableView("No reservations", systemImage: "calendar",
                    description: Text("Reserve a lab from Home → LabOS."))
            } else {
                List {
                    ForEach(store.bookings.sorted(by: { $0.start < $1.start })) { booking in
                        VStack(alignment: .leading, spacing: 8) {
                            Text(booking.labName).font(.headline)
                            Text(booking.start.formatted(date: .abbreviated, time: .shortened))
                                .font(.subheadline).foregroundStyle(.secondary)
                            Button("Cancel booking", role: .destructive) {
                                store.cancel(booking)
                            }
                        }.padding(.vertical, 5)
                    }
                }
            }
        }
        .navigationTitle("My Bookings")
    }
}
