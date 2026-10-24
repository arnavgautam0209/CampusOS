import Foundation
import Combine

protocol InventoryService {
    func fetchInventory() async throws -> [InventoryItem]
    func fetchMyLoans() async throws -> [EquipmentLoan]
    /// Staff only: everything out on loan or reported damaged/missing.
    func fetchAllLoans() async throws -> [EquipmentLoan]
    func borrow(equipmentId: String, quantity: Int, days: Int) async throws -> EquipmentLoan
    func returnLoan(id: Int, condition: EquipmentLoan.Condition, note: String) async throws -> EquipmentLoan
}

struct APIInventoryService: InventoryService {
    let api: APIClient

    func fetchInventory() async throws -> [InventoryItem] {
        try await api.get("inventory/", authenticated: false)
    }

    func fetchMyLoans() async throws -> [EquipmentLoan] {
        try await api.get("inventory/loans/", authenticated: true)
    }

    func fetchAllLoans() async throws -> [EquipmentLoan] {
        try await api.get("inventory/loans/?scope=all", authenticated: true)
    }

    func borrow(equipmentId: String, quantity: Int, days: Int) async throws -> EquipmentLoan {
        struct Request: Encodable { let equipmentId: String; let quantity: Int; let days: Int }
        return try await api.post("inventory/loans/",
                                  body: Request(equipmentId: equipmentId, quantity: quantity, days: days),
                                  authenticated: true)
    }

    func returnLoan(id: Int, condition: EquipmentLoan.Condition, note: String) async throws -> EquipmentLoan {
        struct Request: Encodable { let condition: String; let note: String }
        return try await api.post("inventory/loans/\(id)/return/",
                                  body: Request(condition: condition.rawValue, note: note), authenticated: true)
    }
}

/// AssetX: live stock and loans. The server checks stock, certifications and
/// ownership on every borrow and return; this store only shows its answers.
@MainActor
final class InventoryStore: ObservableObject {
    @Published private(set) var items: [InventoryItem] = []
    @Published private(set) var myLoans: [EquipmentLoan] = []
    @Published private(set) var allLoans: [EquipmentLoan] = []
    @Published private(set) var loadState: LoadState = .idle

    private let service: InventoryService

    init(service: InventoryService) {
        self.service = service
    }

    /// Items grouped by lab, in the server's order.
    var itemsByLab: [(lab: String, items: [InventoryItem])] {
        var order: [String] = []
        var groups: [String: [InventoryItem]] = [:]
        for item in items {
            if groups[item.labName] == nil { order.append(item.labName) }
            groups[item.labName, default: []].append(item)
        }
        return order.map { ($0, groups[$0] ?? []) }
    }

    var activeLoans: [EquipmentLoan] {
        myLoans.filter { $0.status == .active }.sorted { $0.dueAt < $1.dueAt }
    }

    func load(signedIn: Bool, staff: Bool) async {
        loadState = .loading
        do {
            items = try await service.fetchInventory()
            myLoans = signedIn ? try await service.fetchMyLoans() : []
            allLoans = staff ? try await service.fetchAllLoans() : []
            loadState = .loaded
        } catch {
            loadState = .failed(error.localizedDescription)
        }
    }

    func borrow(_ item: InventoryItem, quantity: Int, days: Int) async throws {
        let loan = try await service.borrow(equipmentId: item.id, quantity: quantity, days: days)
        myLoans.insert(loan, at: 0)
        await refreshStock()
    }

    func returnLoan(_ loan: EquipmentLoan, condition: EquipmentLoan.Condition, note: String) async throws {
        let updated = try await service.returnLoan(id: loan.id, condition: condition,
                                                   note: note.trimmingCharacters(in: .whitespacesAndNewlines))
        if let index = myLoans.firstIndex(where: { $0.id == updated.id }) {
            myLoans[index] = updated
        }
        // Staff list shows what's out or reported: keep reports, drop clean returns.
        if let index = allLoans.firstIndex(where: { $0.id == updated.id }) {
            if updated.status == .reported {
                allLoans[index] = updated
            } else {
                allLoans.remove(at: index)
            }
        }
        await refreshStock()
    }

    func reset() {
        myLoans = []
        allLoans = []
        if loadState != .loading { loadState = .idle }
    }

    /// Stock changed on the server; reload counts without disturbing the screen.
    private func refreshStock() async {
        if let fresh = try? await service.fetchInventory() {
            items = fresh
        }
    }
}
