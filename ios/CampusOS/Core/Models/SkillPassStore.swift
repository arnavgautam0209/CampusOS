import Foundation
import Combine

/// SkillPass catalogue plus the signed-in student's certification records.
/// Display only: the server decides access when a booking is made.
@MainActor
final class SkillPassStore: ObservableObject {
    @Published private(set) var catalog: [Certification] = []
    @Published private(set) var records: [CertificationRecord] = []
    @Published private(set) var loadState: LoadState = .idle
    @Published private(set) var requestingID: String?
    /// Faculty review queue: requests waiting for approval.
    @Published private(set) var pendingReviews: [CertificationRecord] = []
    @Published private(set) var reviewState: LoadState = .idle
    @Published private(set) var reviewingID: Int?

    private let service: SkillPassService
    /// Whether the last successful load included the student's records.
    private var loadedSignedIn: Bool?

    init(service: SkillPassService) {
        self.service = service
    }

    func load(signedIn: Bool) async {
        loadState = .loading
        do {
            catalog = try await service.fetchCatalog()
            records = signedIn ? try await service.fetchMyRecords() : []
            loadedSignedIn = signedIn
            loadState = .loaded
        } catch {
            loadState = .failed(error.localizedDescription)
        }
    }

    /// Loads once, and again whenever the user signs in or out.
    func loadIfNeeded(signedIn: Bool) async {
        guard !loadState.isLoading, catalog.isEmpty || loadedSignedIn != signedIn else { return }
        await load(signedIn: signedIn)
    }

    func loadReviews() async {
        reviewState = .loading
        do {
            pendingReviews = try await service.fetchPendingReviews()
            reviewState = .loaded
        } catch {
            reviewState = .failed(error.localizedDescription)
        }
    }

    /// The server records who approved and sets the expiry; self-approval is refused there.
    func approve(_ record: CertificationRecord) async throws {
        try await review(record) { try await self.service.approve(recordID: record.id) }
    }

    func decline(_ record: CertificationRecord) async throws {
        try await review(record) { try await self.service.decline(recordID: record.id) }
    }

    private func review(_ record: CertificationRecord,
                        _ action: () async throws -> CertificationRecord) async throws {
        reviewingID = record.id
        defer { reviewingID = nil }
        _ = try await action()
        pendingReviews.removeAll { $0.id == record.id }
    }

    func reset() {
        pendingReviews = []
        reviewState = .idle
        records = []
        loadedSignedIn = nil
        if loadState != .loading { loadState = .idle }
    }

    func certification(id: String) -> Certification? {
        catalog.first { $0.id == id }
    }

    func standing(for certificationID: String) -> CertificationStanding {
        CertificationStanding(record: records.first { $0.certification.id == certificationID })
    }

    func request(_ certification: Certification) async throws {
        requestingID = certification.id
        defer { requestingID = nil }
        let record = try await service.requestCertification(id: certification.id)
        if let index = records.firstIndex(where: { $0.id == record.id }) {
            records[index] = record
        } else {
            records.append(record)
        }
    }
}
