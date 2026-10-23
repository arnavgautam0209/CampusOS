import SwiftUI

struct MyBookingsView: View {
    @EnvironmentObject private var store: BookingStore

    var body: some View {
        Group {
            if store.bookings.isEmpty {
                ContentUnavailableView("No bookings yet", systemImage: "calendar.badge.clock",
                                       description: Text("Book a laboratory from LabOS to see it here."))
            } else {
                List {
                    ForEach(store.bookings.sorted(by: { $0.start < $1.start })) { item in
                        VStack(alignment: .leading, spacing: 8) {
                            Text(item.labName).font(.headline)
                            Label(item.start.formatted(date: .abbreviated, time: .shortened),
                                  systemImage: "calendar")
                                .font(.subheadline).foregroundStyle(.secondary)
                            Text("Ends: \(item.end.formatted(date: .omitted, time: .shortened))")
                                .font(.caption).foregroundStyle(.secondary)
                            Button("Cancel Booking", role: .destructive) { store.cancel(item) }
                        }
                        .padding(.vertical, 6)
                    }
                }
            }
        }
        .navigationTitle("My Bookings")
    }
}
