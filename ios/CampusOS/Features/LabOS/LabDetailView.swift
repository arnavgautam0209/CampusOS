import SwiftUI

struct LabDetailView: View {
    let lab: Lab

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                Image(systemName: lab.symbol)
                    .font(.system(size: 54))
                    .foregroundStyle(.indigo)
                    .frame(maxWidth: .infinity, minHeight: 140)
                    .background(.indigo.opacity(0.09), in: RoundedRectangle(cornerRadius: 18))
                Text(lab.name).font(.largeTitle.bold())
                Label(lab.location, systemImage: "mappin.and.ellipse")
                    .foregroundStyle(.secondary)
                Label("Capacity: \(lab.capacity)", systemImage: "person.3")
                StatusBadge(text: lab.isOpenForBooking ? "Open for bookings" : "Currently closed",
                            color: lab.isOpenForBooking ? .green : .red)
                Divider()
                Text("Equipment").font(.title2.bold())
                ForEach(lab.equipment) { item in
                    HStack {
                        Image(systemName: item.isAvailable ? "checkmark.circle.fill" : "xmark.circle.fill")
                            .foregroundStyle(item.isAvailable ? .green : .red)
                        Text(item.name)
                        Spacer()
                        Text(item.isAvailable ? "Available" : "Unavailable")
                            .font(.caption).foregroundStyle(.secondary)
                    }
                }
                Divider()
                NavigationLink { LabBookingView(lab: lab) } label: {
                    Text("Reserve Laboratory")
                        .font(.headline)
                        .frame(maxWidth: .infinity)
                        .padding()
                }
                .buttonStyle(.borderedProminent)
                .disabled(!lab.isOpenForBooking)
            }
            .padding()
        }
        .navigationTitle("Lab Details")
        .navigationBarTitleDisplayMode(.inline)
    }
}
