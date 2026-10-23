import SwiftUI

struct LabOSView: View {
    @EnvironmentObject private var labStore: LabStore

    var body: some View {
        Group {
            if labStore.labs.isEmpty {
                emptyState
            } else {
                labList
            }
        }
        .navigationTitle("LabOS")
        .task { await labStore.loadIfNeeded() }
    }

    @ViewBuilder
    private var emptyState: some View {
        if let message = labStore.loadState.errorMessage {
            ContentUnavailableView {
                Label("Can't Load Labs", systemImage: "wifi.exclamationmark")
            } description: {
                Text(message)
            } actions: {
                Button("Try Again") { Task { await labStore.load() } }
                    .buttonStyle(.borderedProminent)
            }
        } else if labStore.loadState == .loaded {
            ContentUnavailableView("No Labs Yet", systemImage: "building.2",
                                   description: Text("The server has no laboratories listed."))
        } else {
            ProgressView("Loading labs…")
        }
    }

    private var labList: some View {
        let labs = labStore.labs
        return ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                Text("Find an available lab and reserve a workstation.")
                    .foregroundStyle(.secondary)
                if let message = labStore.loadState.errorMessage {
                    Label(message, systemImage: "exclamationmark.triangle.fill")
                        .font(.caption).foregroundStyle(.orange)
                }
                HStack(spacing: 12) {
                    metric("Total Labs", "\(labs.count)", "building.2")
                    metric("Bookable", "\(labs.filter { $0.isOpenForBooking }.count)", "checkmark.circle")
                }
                Text("Explore Laboratories").font(.title2.bold())
                ForEach(labs) { lab in
                    NavigationLink { LabDetailView(lab: lab) } label: {
                        HStack(spacing: 12) {
                            Image(systemName: lab.symbol)
                                .font(.title2).foregroundStyle(.indigo)
                                .frame(width: 45, height: 45)
                                .background(.indigo.opacity(0.1), in: RoundedRectangle(cornerRadius: 12))
                            VStack(alignment: .leading, spacing: 5) {
                                Text(lab.name).font(.headline)
                                Text(lab.location).font(.caption).foregroundStyle(.secondary)
                                Label("\(lab.capacity) seats", systemImage: "person.2")
                                    .font(.caption).foregroundStyle(.secondary)
                            }
                            Spacer(minLength: 3)
                            StatusBadge(text: lab.isOpenForBooking ? "Bookable" : "Closed",
                                        color: lab.isOpenForBooking ? .green : .red)
                        }
                        .foregroundStyle(.primary)
                        .padding()
                        .background(Color(.secondarySystemBackground), in: RoundedRectangle(cornerRadius: 16))
                    }
                }
                Text("Live data from the CampusOS server. Pull down to refresh.")
                    .font(.caption).foregroundStyle(.secondary)
            }
            .padding()
        }
        .refreshable { await labStore.load() }
    }

    private func metric(_ title: String, _ value: String, _ icon: String) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Image(systemName: icon).foregroundStyle(.indigo)
            Text(value).font(.title.bold())
            Text(title).font(.caption).foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding()
        .background(Color(.secondarySystemBackground), in: RoundedRectangle(cornerRadius: 15))
    }
}
