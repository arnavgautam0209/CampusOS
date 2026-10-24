import Foundation

/// One equipment item with live stock, from GET /api/v1/inventory/.
struct InventoryItem: Codable, Identifiable, Equatable {
    let id: String
    let name: String
    let category: String
    let labId: String
    let labName: String
    let totalQuantity: Int
    let availableQuantity: Int
    let isLowStock: Bool
    /// Students may take it out of the lab; otherwise it's used in the lab only.
    let isLoanable: Bool
    let underMaintenance: Bool
    let requiredCertifications: [String]

    var canBorrow: Bool { isLoanable && !underMaintenance && availableQuantity > 0 }
}

/// Units of one item borrowed by someone (GET/POST /api/v1/inventory/loans/).
struct EquipmentLoan: Codable, Identifiable, Equatable {
    enum Status: String, Codable {
        case active, returned, reported, resolved, other

        init(from decoder: Decoder) throws {
            let raw = try decoder.singleValueContainer().decode(String.self)
            self = Status(rawValue: raw) ?? .other
        }
    }

    enum Condition: String, Codable, CaseIterable, Identifiable {
        case ok, damaged, missing

        var id: String { rawValue }
        var label: String {
            switch self {
            case .ok: return "All good"
            case .damaged: return "Damaged"
            case .missing: return "Missing"
            }
        }
    }

    let id: Int
    let equipmentId: String
    let equipmentName: String
    let labName: String
    let quantity: Int
    let status: Status
    let borrower: String
    let username: String
    let checkedOutAt: Date
    let dueAt: Date
    let returnedAt: Date?
    /// Computed by the server when the list was fetched.
    let isOverdue: Bool
    /// "", "ok", "damaged" or "missing".
    let condition: String
    let note: String
}
