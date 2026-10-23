import SwiftUI

/// A student's own attendance, updating live while open.
struct MyAttendanceView: View {
    @EnvironmentObject private var store: AttendanceStore

    var body: some View {
        content
            .task { await store.poll(staff: false) }
    }

    @ViewBuilder
    private var content: some View {
        if store.myRecords.isEmpty, store.lastUpdated == nil, let message = store.loadState.errorMessage {
            ContentUnavailableView {
                Label("Can't Load Attendance", systemImage: "wifi.exclamationmark")
            } description: {
                Text(message)
            } actions: {
                Button("Try Again") { Task { await store.refreshMine() } }
                    .buttonStyle(.borderedProminent)
            }
        } else if store.lastUpdated == nil {
            ProgressView("Loading your attendance…")
        } else {
            List {
                Section {
                    LiveStatusRow(lastUpdated: store.lastUpdated, errorMessage: store.loadState.errorMessage)
                }
                Section {
                    if store.myRecords.isEmpty {
                        Text("No attendance yet. Tap your card on the classroom reader during a session.")
                            .foregroundStyle(.secondary)
                    }
                    ForEach(store.myRecords) { record in
                        MyAttendanceRow(record: record, isNew: store.newRecordIDs.contains(record.id))
                            .listRowBackground(store.newRecordIDs.contains(record.id) ? Color.green.opacity(0.15) : nil)
                    }
                } header: {
                    Text("My Attendance")
                } footer: {
                    Text("A card tap shows your card was present. Your teacher may also check attendance in person.")
                }
            }
            .animation(.default, value: store.myRecords)
            .refreshable { await store.refreshMine() }
        }
    }
}

private struct MyAttendanceRow: View {
    let record: MyAttendance
    let isNew: Bool

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: "checkmark.circle.fill")
                .font(.title3).foregroundStyle(.green)
            VStack(alignment: .leading, spacing: 2) {
                Text(record.session).font(.headline)
                Text(record.classroomName).font(.caption).foregroundStyle(.secondary)
                Text(record.markedAt.formatted(date: .abbreviated, time: .shortened)
                     + (record.source == .manual ? " · added by faculty" : " · card tap"))
                    .font(.caption).foregroundStyle(.secondary)
            }
            Spacer()
            if isNew {
                StatusBadge(text: "Just now", color: .green)
            }
        }
        .accessibilityElement(children: .combine)
    }
}
