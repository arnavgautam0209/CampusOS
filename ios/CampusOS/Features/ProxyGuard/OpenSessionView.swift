import SwiftUI

/// Faculty sheet: pick a room and title, then open an attendance session there.
struct OpenSessionView: View {
    let classrooms: [LiveClassroom]

    @EnvironmentObject private var store: AttendanceStore
    @Environment(\.dismiss) private var dismiss
    @State private var classroomId: String
    @State private var title = ""
    @State private var errorMessage: String?

    init(classrooms: [LiveClassroom]) {
        self.classrooms = classrooms
        _classroomId = State(initialValue: classrooms.first?.id ?? "")
    }

    private var canOpen: Bool {
        !classroomId.isEmpty && !title.trimmingCharacters(in: .whitespaces).isEmpty && !store.isChangingSession
    }

    var body: some View {
        Form {
            Section {
                Picker("Classroom", selection: $classroomId) {
                    ForEach(classrooms) { room in
                        Text(room.name).tag(room.id)
                    }
                }
                TextField("Title, e.g. CS201 Lecture 5", text: $title)
                    .submitLabel(.done)
                    .onSubmit { if canOpen { Task { await open() } } }
            } footer: {
                Text("Readers in this room start marking attendance as soon as the session opens.")
            }
            if let errorMessage {
                Section {
                    Label(errorMessage, systemImage: "exclamationmark.triangle.fill")
                        .foregroundStyle(.red)
                }
            }
        }
        .navigationTitle("Open Session")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .cancellationAction) {
                Button("Cancel") { dismiss() }
            }
            ToolbarItem(placement: .confirmationAction) {
                if store.isChangingSession {
                    ProgressView()
                } else {
                    Button("Open") { Task { await open() } }
                        .disabled(!canOpen)
                }
            }
        }
        .interactiveDismissDisabled(store.isChangingSession)
    }

    private func open() async {
        errorMessage = nil
        do {
            try await store.openSession(classroomId: classroomId, title: title)
            dismiss()
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}
