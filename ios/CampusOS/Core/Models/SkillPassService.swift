import Foundation

protocol SkillPassService {
    func fetchCatalog() async throws -> [Certification]
    func fetchMyRecords() async throws -> [CertificationRecord]
    func requestCertification(id: String) async throws -> CertificationRecord
    // Faculty only (the server returns 403 for students).
    func fetchPendingReviews() async throws -> [CertificationRecord]
    func approve(recordID: Int) async throws -> CertificationRecord
    func decline(recordID: Int) async throws -> CertificationRecord
}

struct APISkillPassService: SkillPassService {
    let api: APIClient

    func fetchCatalog() async throws -> [Certification] {
        try await api.get("certifications/", authenticated: false)
    }

    func fetchMyRecords() async throws -> [CertificationRecord] {
        try await api.get("certifications/mine/", authenticated: true)
    }

    func requestCertification(id: String) async throws -> CertificationRecord {
        try await api.post("certifications/\(id)/request/", authenticated: true)
    }

    func fetchPendingReviews() async throws -> [CertificationRecord] {
        try await api.get("certification-records/?status=pending", authenticated: true)
    }

    func approve(recordID: Int) async throws -> CertificationRecord {
        try await api.post("certification-records/\(recordID)/approve/", authenticated: true)
    }

    /// Declining a request revokes it; the student can request again later.
    func decline(recordID: Int) async throws -> CertificationRecord {
        try await api.post("certification-records/\(recordID)/revoke/", authenticated: true)
    }
}
