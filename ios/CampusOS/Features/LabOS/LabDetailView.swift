import SwiftUI

struct LabDetailView: View {
    let lab: Lab
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                Image(systemName: lab.symbol).font(.system(size: 52))
                    .foregroundStyle(.indigo)
                    .frame(maxWidth: .infinity)
                    .padding(28)
                    .background(Color.indigo.opacity(0.08))
                    .clipShape(RoundedRectangle(cornerRadius: 18))
                Text(lab.name).font(.largeTitle.bold())
                Label(lab.location, systemImage: "mappin")
                Label("\(lab.capacity) seats", systemImage: "person.2")
                StatusBadge(text: lab.isOpenForBooking ? "Accepting bookings" : "Unavailable",
                            available: lab.isOpenForBooking)
                Divider()
                Text("Equipment").font(.title2.bold())
                ForEach(lab.equipment, id: \.self) { item in
                    Label(item, systemImage: "checkmark.circle")
                }
                Divider()
                NavigationLink {
                    LabBookingView(lab: lab)
                } label: {
                    Text("Reserve Lab").frame(maxWidth: .infinity).padding(10)
                }
                .buttonStyle(.borderedProminent)
                .disabled(!lab.isOpenForBooking)
                Text("Demo only: bookings are stored on this device.")
                    .font(.caption).foregroundStyle(.secondary)
            }.padding()
        }
        .navigationTitle("Lab Details")
        .navigationBarTitleDisplayMode(.inline)
    }
}
