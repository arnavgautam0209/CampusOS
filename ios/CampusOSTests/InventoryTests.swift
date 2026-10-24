import Foundation
import Testing
@testable import CampusOS

/// Real responses from GET /api/v1/inventory/ and POST /api/v1/inventory/loans/.
let inventoryFixtureJSON = #"""
[
 {
  "id": "EQ008",
  "name": "Arduino Uno Boards",
  "category": "Embedded",
  "labId": "LAB001",
  "labName": "Robotics Lab",
  "totalQuantity": 25,
  "availableQuantity": 23,
  "isLowStock": false,
  "isLoanable": true,
  "underMaintenance": false,
  "requiredCertifications": []
 },
 {
  "id": "EQ002",
  "name": "Robotic Arm",
  "category": "Robotics",
  "labId": "LAB001",
  "labName": "Robotics Lab",
  "totalQuantity": 1,
  "availableQuantity": 1,
  "isLowStock": true,
  "isLoanable": false,
  "underMaintenance": false,
  "requiredCertifications": [
   "CERT-ROBOT-ARM"
  ]
 },
 {
  "id": "EQ004",
  "name": "Oscilloscope",
  "category": "Testing",
  "labId": "LAB002",
  "labName": "Electronics Lab",
  "totalQuantity": 8,
  "availableQuantity": 8,
  "isLowStock": false,
  "isLoanable": true,
  "underMaintenance": false,
  "requiredCertifications": [
   "CERT-ELEC-BASIC"
  ]
 },
 {
  "id": "EQ006",
  "name": "3D Printer",
  "category": "Fabrication",
  "labId": "LAB003",
  "labName": "3D Printing Lab",
  "totalQuantity": 1,
  "availableQuantity": 0,
  "isLowStock": false,
  "isLoanable": false,
  "underMaintenance": true,
  "requiredCertifications": [
   "CERT-3DP"
  ]
 }
]
"""#

let loanFixtureJSON = #"""
{
 "id": 1,
 "equipmentId": "EQ008",
 "equipmentName": "Arduino Uno Boards",
 "labName": "Robotics Lab",
 "quantity": 2,
 "status": "active",
 "borrower": "Fixture Borrower",
 "username": "fixture_borrower",
 "checkedOutAt": "2026-10-24T06:31:52.117331+05:30",
 "dueAt": "2026-10-27T06:31:52.117331+05:30",
 "returnedAt": null,
 "isOverdue": false,
 "condition": "",
 "note": ""
}
"""#

func inventoryFixture() throws -> [InventoryItem] {
    try JSONDecoder.campusOS.decode([InventoryItem].self, from: Data(inventoryFixtureJSON.utf8))
}

func loanFixture() throws -> EquipmentLoan {
    try JSONDecoder.campusOS.decode(EquipmentLoan.self, from: Data(loanFixtureJSON.utf8))
}

final class FakeInventoryService: InventoryService {
    var items: [InventoryItem] = []
    var mine: [EquipmentLoan] = []
    var all: [EquipmentLoan] = []
    var borrowResult: Result<EquipmentLoan, Error> = .failure(APIError.badResponse)
    var returnResult: Result<EquipmentLoan, Error> = .failure(APIError.badResponse)
    private(set) var inventoryFetches = 0
    private(set) var myLoanFetches = 0
    private(set) var allLoanFetches = 0
    private(set) var borrowed: [(String, Int, Int)] = []
    private(set) var returned: [(Int, EquipmentLoan.Condition, String)] = []

    func fetchInventory() async throws -> [InventoryItem] { inventoryFetches += 1; return items }
    func fetchMyLoans() async throws -> [EquipmentLoan] { myLoanFetches += 1; return mine }
    func fetchAllLoans() async throws -> [EquipmentLoan] { allLoanFetches += 1; return all }

    func borrow(equipmentId: String, quantity: Int, days: Int) async throws -> EquipmentLoan {
        borrowed.append((equipmentId, quantity, days))
        return try borrowResult.get()
    }

    func returnLoan(id: Int, condition: EquipmentLoan.Condition, note: String) async throws -> EquipmentLoan {
        returned.append((id, condition, note))
        return try returnResult.get()
    }
}

/// A copy of `loan` with a different status (EquipmentLoan is immutable).
func loan(_ loan: EquipmentLoan, status: EquipmentLoan.Status) throws -> EquipmentLoan {
    var json = try #require(try JSONSerialization.jsonObject(with: JSONEncoder.campusOS.encode(loan)) as? [String: Any])
    json["status"] = status.rawValue
    return try JSONDecoder.campusOS.decode(EquipmentLoan.self, from: JSONSerialization.data(withJSONObject: json))
}

@Suite("Inventory decoding")
struct InventoryDecodingTests {
    @Test func decodesRealInventory() throws {
        let items = try inventoryFixture()
        let arduino = try #require(items.first { $0.id == "EQ008" })
        #expect((arduino.totalQuantity, arduino.availableQuantity) == (25, 23))
        #expect(arduino.isLoanable && arduino.canBorrow)

        let printer = try #require(items.first { $0.id == "EQ006" })
        #expect(printer.underMaintenance && !printer.canBorrow)
        #expect(try #require(items.first { $0.id == "EQ002" }).isLoanable == false)
        #expect(try #require(items.first { $0.id == "EQ004" }).requiredCertifications == ["CERT-ELEC-BASIC"])
    }

    @Test func decodesRealLoan() throws {
        let loan = try loanFixture()
        #expect(loan.equipmentId == "EQ008")
        #expect(loan.quantity == 2)
        #expect(loan.status == .active)
        #expect(!loan.isOverdue)
        #expect(loan.dueAt.timeIntervalSince(loan.checkedOutAt) == 3 * 24 * 3600)
    }
}

@MainActor
@Suite("InventoryStore")
struct InventoryStoreTests {
    private let service = FakeInventoryService()

    init() throws {
        service.items = try inventoryFixture()
    }

    @Test func signedOutLoadsStockOnly() async {
        let store = InventoryStore(service: service)
        await store.load(signedIn: false, staff: false)
        #expect(store.items.count == 4)
        #expect(service.myLoanFetches == 0 && service.allLoanFetches == 0)
        #expect(store.loadState == .loaded)
    }

    @Test func staffAlsoLoadEveryLoan() async throws {
        service.all = [try loanFixture()]
        let store = InventoryStore(service: service)
        await store.load(signedIn: true, staff: true)
        #expect(store.allLoans.count == 1)
        #expect(service.myLoanFetches == 1)
    }

    @Test func groupsItemsByLab() async {
        let store = InventoryStore(service: service)
        await store.load(signedIn: false, staff: false)
        #expect(store.itemsByLab.map(\.lab) == ["Robotics Lab", "Electronics Lab", "3D Printing Lab"])
    }

    @Test func borrowAddsLoanAndRefreshesStock() async throws {
        service.borrowResult = .success(try loanFixture())
        let store = InventoryStore(service: service)
        await store.load(signedIn: true, staff: false)
        let arduino = try #require(store.items.first { $0.id == "EQ008" })

        try await store.borrow(arduino, quantity: 2, days: 3)

        #expect(service.borrowed.first?.0 == "EQ008")
        #expect(service.borrowed.first?.1 == 2 && service.borrowed.first?.2 == 3)
        #expect(store.activeLoans.map(\.equipmentId) == ["EQ008"])
        #expect(service.inventoryFetches == 2)
    }

    @Test func refusedBorrowChangesNothing() async throws {
        service.borrowResult = .failure(APIError.conflict("Only 1 Arduino Uno Boards available right now."))
        let store = InventoryStore(service: service)
        await store.load(signedIn: true, staff: false)

        await #expect(throws: APIError.conflict("Only 1 Arduino Uno Boards available right now.")) {
            try await store.borrow(store.items[0], quantity: 5, days: 1)
        }
        #expect(store.myLoans.isEmpty)
    }

    @Test func returningUpdatesMyLoansAndStaffList() async throws {
        let active = try loanFixture()
        service.mine = [active]
        service.all = [active]
        service.returnResult = .success(try loan(active, status: .returned))
        let store = InventoryStore(service: service)
        await store.load(signedIn: true, staff: true)

        try await store.returnLoan(active, condition: .ok, note: "  ")

        #expect(service.returned.first?.2 == "")
        #expect(store.activeLoans.isEmpty)
        #expect(store.allLoans.isEmpty)
    }

    @Test func damagedReportStaysOnStaffList() async throws {
        let active = try loanFixture()
        service.mine = [active]
        service.all = [active]
        service.returnResult = .success(try loan(active, status: .reported))
        let store = InventoryStore(service: service)
        await store.load(signedIn: true, staff: true)

        try await store.returnLoan(active, condition: .damaged, note: "Pins bent")

        #expect(service.returned.first?.1 == .damaged)
        #expect(store.allLoans.first?.status == .reported)
        #expect(store.activeLoans.isEmpty)
    }

    @Test func resetForgetsLoans() async throws {
        service.mine = [try loanFixture()]
        let store = InventoryStore(service: service)
        await store.load(signedIn: true, staff: false)
        store.reset()
        #expect(store.myLoans.isEmpty)
        #expect(!store.items.isEmpty)  // stock is public
    }
}
