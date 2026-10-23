import Foundation

protocol SkillPassService {
    func fetchCatalog() async throws -> [Certification]
    func fetchMyRecords() async throws -> [CertificationRecord]
    func requestCertification(id: String) async throws -> CertificationRecord
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
}
