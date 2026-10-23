import Foundation

/// A practical skill faculty can certify (GET /api/v1/certifications/).
struct Certification: Identifiable, Codable, Hashable {
    let id: String
    let name: String
    let description: String
    let validityDays: Int?
}

/// The signed-in student's record for one certification (GET /api/v1/certifications/mine/).
struct CertificationRecord: Identifiable, Codable, Equatable {
    enum Status: String, Codable {
        case pending, approved, revoked
    }

    let id: Int
    let certification: Certification
    let status: Status
    /// Computed by the server: approved and not yet expired.
    let isValid: Bool
    let requestedAt: Date
    let approvedBy: String?
    let approvedAt: Date?
    let expiresAt: Date?
}

/// Where a student stands for one certification, as shown in the app.
enum CertificationStanding: Equatable {
    case notRequested
    case pending
    case certified(expiresAt: Date?)
    case expired
    case revoked

    init(record: CertificationRecord?) {
        guard let record else { self = .notRequested; return }
        switch record.status {
        case .pending: self = .pending
        case .revoked: self = .revoked
        case .approved: self = record.isValid ? .certified(expiresAt: record.expiresAt) : .expired
        }
    }

    var isCertified: Bool {
        if case .certified = self { return true }
        return false
    }

    /// A student may ask for training (again) unless they're certified or already waiting.
    var canRequest: Bool {
        switch self {
        case .notRequested, .expired, .revoked: return true
        case .pending, .certified: return false
        }
    }

    var label: String {
        switch self {
        case .notRequested: return "Not certified"
        case .pending: return "Awaiting faculty"
        case .certified: return "Certified"
        case .expired: return "Expired"
        case .revoked: return "Revoked"
        }
    }

    var requestButtonTitle: String {
        self == .notRequested ? "Request Training" : "Request Renewal"
    }
}
