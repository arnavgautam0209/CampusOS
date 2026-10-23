import SwiftUI

struct LabOSView: View {
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                Text("Find labs, view equipment and reserve one-hour sessions.")
                    .foregroundStyle(.secondary)
                HStack {
                    Label("\(Lab.examples.count) labs", systemImage: "building.2")
                    Spacer()
                    Label("\(Lab.examples.filter(\.isOpenForBooking).count) open",
                          systemImage: "checkmark.circle")
                }.font(.subheadline)
                ForEach(Lab.examples) { lab in
                    NavigationLink {
                        LabDetailView(lab: lab)
                    } label: {
                        VStack(alignment: .leading, spacing: 10) {
                            HStack {
                                Image(systemName: lab.symbol).font(.title)
                                    .foregroundStyle(.indigo)
                                    .frame(width: 42)
                                VStack(alignment: .leading, spacing: 4) {
                                    Text(lab.name).font(.headline)
                                    Text(lab.location).font(.caption)
                                        .foregroundStyle(.secondary)
                                }
                                Spacer()
                                Image(systemName: "chevron.right")
                            }
                            HStack {
                                Label("\(lab.capacity) seats", systemImage: "person.2")
                                Spacer()
                                StatusBadge(text: lab.isOpenForBooking ? "Open" : "Closed",
                                            available: lab.isOpenForBooking)
                            }.font(.caption)
                        }
                        .padding()
                        .background(Color(.secondarySystemBackground))
                        .clipShape(RoundedRectangle(cornerRadius: 16))
                    }
                    .buttonStyle(.plain)
                }
            }.padding()
        }
        .navigationTitle("LabOS")
    }
}
