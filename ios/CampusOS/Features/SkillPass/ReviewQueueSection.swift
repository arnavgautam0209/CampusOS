import SwiftUI

/// Faculty only: SkillPass requests waiting for approval. The server enforces
/// staff access and refuses self-approval; this just presents the queue.
struct ReviewQueueSection: View {
    @EnvironmentObject private var skillPass: SkillPassStore
    @EnvironmentObject private var auth: AuthManager
    @State private var errorMessage: String?

    var body: some View {
        Section {
            if skillPass.pendingReviews.isEmpty {
                if skillPass.reviewState == .loading {
                    ProgressView()
                } else if let message = skillPass.reviewState.errorMessage {
                    Label(message, systemImage: "exclamationmark.triangle.fill")
                        .font(.caption).foregroundStyle(.orange)
                } else {
                    Text("No requests waiting.").foregroundStyle(.secondary)
                }
            }
            ForEach(skillPass.pendingReviews) { record in
                ReviewRow(record: record,
                          isOwn: record.username != nil && record.username == auth.currentUser?.username,
                          isBusy: skillPass.reviewingID == record.id,
                          isDisabled: skillPass.reviewingID != nil,
                          approve: { Task { await act { try await skillPass.approve(record) } } },
                          decline: { Task { await act { try await skillPass.decline(record) } } })
            }
        } header: {
            HStack {
                Text("Requests to Review")
                if !skillPass.pendingReviews.isEmpty {
                    StatusBadge(text: "\(skillPass.pendingReviews.count)", color: .orange)
                }
            }
        } footer: {
            Text("Approving certifies the student for the certification's validity period and is recorded under your name.")
        }
        .alert("Couldn't Update Request", isPresented: Binding(
            get: { errorMessage != nil }, set: { if !$0 { errorMessage = nil } })
        ) {
            Button("OK", role: .cancel) {}
        } message: {
            Text(errorMessage ?? "")
        }
    }

    private func act(_ action: () async throws -> Void) async {
        do {
            try await action()
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

private struct ReviewRow: View {
    let record: CertificationRecord
    let isOwn: Bool
    let isBusy: Bool
    let isDisabled: Bool
    let approve: () -> Void
    let decline: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            VStack(alignment: .leading, spacing: 2) {
                Text(record.studentName ?? record.username ?? "Student").font(.headline)
                if let username = record.username, username != record.studentName {
                    Text(username).font(.caption).foregroundStyle(.secondary)
                }
            }
            Label(record.certification.name, systemImage: "seal")
                .font(.subheadline)
            Text("Requested \(record.requestedAt.formatted(.relative(presentation: .named)))")
                .font(.caption).foregroundStyle(.secondary)
            if isOwn {
                Text("Your request: another faculty member must approve it.")
                    .font(.caption).foregroundStyle(.secondary)
            } else if isBusy {
                ProgressView()
            } else {
                HStack(spacing: 12) {
                    Button("Approve", action: approve)
                        .buttonStyle(.borderedProminent)
                        .tint(.green)
                    Button("Decline", role: .destructive, action: decline)
                        .buttonStyle(.bordered)
                }
                .disabled(isDisabled)
            }
        }
        .padding(.vertical, 4)
    }
}
