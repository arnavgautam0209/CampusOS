import SwiftUI

struct CertificationStatusBadge: View {
    let standing: CertificationStanding

    var body: some View {
        StatusBadge(text: standing.label, color: color)
    }

    private var color: Color {
        switch standing {
        case .certified: return .green
        case .pending: return .orange
        case .notRequested: return .gray
        case .expired, .revoked: return .red
        }
    }
}

/// One certification with the student's standing and a request button.
/// Used on the SkillPass screen and on lab details.
struct CertificationRow: View {
    let certification: Certification
    var showsDescription = true

    @EnvironmentObject private var skillPass: SkillPassStore
    @EnvironmentObject private var auth: AuthManager
    @State private var errorMessage: String?

    var body: some View {
        let standing = skillPass.standing(for: certification.id)
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .firstTextBaseline) {
                Label(certification.name, systemImage: standing.isCertified ? "checkmark.seal.fill" : "seal")
                    .font(.headline)
                    .foregroundStyle(standing.isCertified ? .green : .primary)
                Spacer(minLength: 8)
                if auth.isSignedIn {
                    CertificationStatusBadge(standing: standing)
                }
            }
            if showsDescription, !certification.description.isEmpty {
                Text(certification.description)
                    .font(.subheadline).foregroundStyle(.secondary)
            }
            if case .certified(let expiresAt?) = standing {
                Text("Valid until \(expiresAt.formatted(date: .abbreviated, time: .omitted))")
                    .font(.caption).foregroundStyle(.secondary)
            } else if standing == .pending {
                Text("Requested. A faculty member must approve your training.")
                    .font(.caption).foregroundStyle(.secondary)
            }
            if auth.isSignedIn, standing.canRequest {
                if skillPass.requestingID == certification.id {
                    ProgressView()
                } else {
                    Button(standing.requestButtonTitle) {
                        Task { await request() }
                    }
                    .buttonStyle(.bordered)
                    .disabled(skillPass.requestingID != nil)
                }
            }
        }
        .padding(.vertical, 4)
        .alert("Couldn't Send Request", isPresented: Binding(
            get: { errorMessage != nil }, set: { if !$0 { errorMessage = nil } })
        ) {
            Button("OK", role: .cancel) {}
        } message: {
            Text(errorMessage ?? "")
        }
    }

    private func request() async {
        do {
            try await skillPass.request(certification)
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}
