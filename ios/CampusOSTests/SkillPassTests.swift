import Foundation
import Testing
@testable import CampusOS

final class FakeSkillPassService: SkillPassService {
    var catalog: [Certification] = []
    var records: [CertificationRecord] = []
    var requestResult: Result<CertificationRecord, Error>?
    private(set) var recordFetches = 0
    private(set) var requestedIDs: [String] = []

    func fetchCatalog() async throws -> [Certification] { catalog }

    func fetchMyRecords() async throws -> [CertificationRecord] {
        recordFetches += 1
        return records
    }

    func requestCertification(id: String) async throws -> CertificationRecord {
        requestedIDs.append(id)
        return try requestResult!.get()
    }
}

private let electronics = Certification(id: "CERT-ELEC-BASIC", name: "Basic Electronics Safety",
                                        description: "Bench safety.", validityDays: 365)
private let soldering = Certification(id: "CERT-SOLDER", name: "Soldering Station Training",
                                      description: "Hot tools.", validityDays: 180)

private func record(_ cert: Certification, _ status: CertificationRecord.Status, valid: Bool = false,
                    id: Int = 1, expiresAt: Date? = nil) -> CertificationRecord {
    CertificationRecord(id: id, certification: cert, status: status, isValid: valid,
                        requestedAt: Date(timeIntervalSince1970: 0), approvedBy: valid ? "faculty" : nil,
                        approvedAt: nil, expiresAt: expiresAt)
}

@Suite("CertificationStanding")
struct CertificationStandingTests {
    @Test func mapsRecordsToStanding() {
        let expiry = Date(timeIntervalSince1970: 2_000_000_000)
        #expect(CertificationStanding(record: nil) == .notRequested)
        #expect(CertificationStanding(record: record(electronics, .pending)) == .pending)
        #expect(CertificationStanding(record: record(electronics, .revoked)) == .revoked)
        #expect(CertificationStanding(record: record(electronics, .approved, valid: true, expiresAt: expiry))
                == .certified(expiresAt: expiry))
        // Approved but past its expiry: the server reports isValid = false.
        #expect(CertificationStanding(record: record(electronics, .approved, valid: false)) == .expired)
    }

    @Test func onlyMissingExpiredOrRevokedCanBeRequested() {
        #expect(CertificationStanding.notRequested.canRequest)
        #expect(CertificationStanding.expired.canRequest)
        #expect(CertificationStanding.revoked.canRequest)
        #expect(!CertificationStanding.pending.canRequest)
        #expect(!CertificationStanding.certified(expiresAt: nil).canRequest)
        #expect(CertificationStanding.notRequested.requestButtonTitle == "Request Training")
        #expect(CertificationStanding.expired.requestButtonTitle == "Request Renewal")
    }
}

@MainActor
@Suite("SkillPassStore")
struct SkillPassStoreTests {
    private let service = FakeSkillPassService()

    init() {
        service.catalog = [electronics, soldering]
    }

    @Test func signedOutLoadsCatalogOnly() async {
        let store = SkillPassStore(service: service)
        await store.load(signedIn: false)

        #expect(store.catalog.map(\.id) == ["CERT-ELEC-BASIC", "CERT-SOLDER"])
        #expect(store.records.isEmpty)
        #expect(service.recordFetches == 0)
        #expect(store.loadState == .loaded)
        #expect(store.certification(id: "CERT-SOLDER")?.name == "Soldering Station Training")
    }

    @Test func signedInLoadsRecordsAndStanding() async {
        service.records = [record(electronics, .approved, valid: true)]
        let store = SkillPassStore(service: service)
        await store.load(signedIn: true)

        #expect(store.standing(for: "CERT-ELEC-BASIC").isCertified)
        #expect(store.standing(for: "CERT-SOLDER") == .notRequested)
    }

    @Test func loadIfNeededReloadsOnlyWhenSignInChanges() async {
        let store = SkillPassStore(service: service)
        await store.loadIfNeeded(signedIn: false)
        await store.loadIfNeeded(signedIn: false)
        #expect(service.recordFetches == 0)

        await store.loadIfNeeded(signedIn: true)
        await store.loadIfNeeded(signedIn: true)
        #expect(service.recordFetches == 1)
    }

    @Test func requestAddsPendingRecord() async throws {
        service.requestResult = .success(record(soldering, .pending, id: 7))
        let store = SkillPassStore(service: service)
        await store.load(signedIn: true)

        try await store.request(soldering)

        #expect(service.requestedIDs == ["CERT-SOLDER"])
        #expect(store.standing(for: "CERT-SOLDER") == .pending)
        #expect(store.requestingID == nil)
    }

    @Test func renewalReplacesExistingRecord() async throws {
        service.records = [record(electronics, .revoked, id: 3)]
        service.requestResult = .success(record(electronics, .pending, id: 3))
        let store = SkillPassStore(service: service)
        await store.load(signedIn: true)

        try await store.request(electronics)

        #expect(store.records.count == 1)
        #expect(store.standing(for: "CERT-ELEC-BASIC") == .pending)
    }

    @Test func failedRequestKeepsStandingAndClearsSpinner() async {
        service.requestResult = .failure(APIError.invalid("You already hold this certification."))
        let store = SkillPassStore(service: service)
        await store.load(signedIn: true)

        await #expect(throws: APIError.invalid("You already hold this certification.")) {
            try await store.request(electronics)
        }
        #expect(store.standing(for: "CERT-ELEC-BASIC") == .notRequested)
        #expect(store.requestingID == nil)
    }

    @Test func resetForgetsRecordsSoNextUserReloads() async {
        service.records = [record(electronics, .approved, valid: true)]
        let store = SkillPassStore(service: service)
        await store.load(signedIn: true)

        store.reset()

        #expect(store.records.isEmpty)
        #expect(store.standing(for: "CERT-ELEC-BASIC") == .notRequested)
        await store.loadIfNeeded(signedIn: true)
        #expect(service.recordFetches == 2)
    }
}

@Suite("SkillPass decoding")
struct SkillPassDecodingTests {
    @Test func decodesServerCertificationRecord() throws {
        // Captured from the Django API.
        let json = """
        {"id":1,"username":"student","certification":{"id":"CERT-ELEC-BASIC","name":"Basic Electronics Safety",
         "description":"Safe use of bench power supplies, oscilloscopes and multimeters.","validityDays":365},
         "status":"approved","isValid":true,"requestedAt":"2026-10-24T00:09:24.368142+05:30",
         "approvedBy":"faculty","approvedAt":"2026-10-24T00:10:01.5+05:30","expiresAt":"2027-10-24T00:10:01.5+05:30"}
        """
        let decoded = try JSONDecoder.campusOS.decode(CertificationRecord.self, from: Data(json.utf8))
        #expect(decoded.certification.validityDays == 365)
        #expect(decoded.approvedBy == "faculty")
        #expect(decoded.expiresAt != nil)
        #expect(CertificationStanding(record: decoded).isCertified)
    }

    @Test func decodesPendingRecordWithNulls() throws {
        let json = """
        {"id":2,"username":"student","certification":{"id":"CERT-3DP","name":"3D Printer Operation",
         "description":"","validityDays":null},"status":"pending","isValid":false,
         "requestedAt":"2026-10-24T00:09:24+05:30","approvedBy":null,"approvedAt":null,"expiresAt":null}
        """
        let decoded = try JSONDecoder.campusOS.decode(CertificationRecord.self, from: Data(json.utf8))
        #expect(decoded.status == .pending)
        #expect(decoded.certification.validityDays == nil)
    }

    @Test func labDecodesRequirementsAndToleratesOlderServers() throws {
        let current = """
        {"id":"LAB002","name":"Electronics Lab","location":"Block B","symbol":"bolt","capacity":40,
         "equipment":[{"id":"EQ004","name":"Oscilloscope","category":"Testing","isAvailable":true,
                       "requiredCertifications":["CERT-ELEC-BASIC"]}],
         "isOpenForBooking":true,"requiredCertifications":["CERT-ELEC-BASIC"]}
        """
        let older = """
        {"id":"LAB001","name":"Robotics Lab","location":"Block A","symbol":"cpu","capacity":30,
         "equipment":[{"id":"EQ001","name":"ESP32 Kits","category":"Embedded","isAvailable":true}],
         "isOpenForBooking":true}
        """
        let lab = try JSONDecoder.campusOS.decode(Lab.self, from: Data(current.utf8))
        #expect(lab.requiredCertifications == ["CERT-ELEC-BASIC"])
        #expect(lab.equipment.first?.requiredCertifications == ["CERT-ELEC-BASIC"])

        let oldLab = try JSONDecoder.campusOS.decode(Lab.self, from: Data(older.utf8))
        #expect(oldLab.requiredCertifications.isEmpty)
        #expect(oldLab.equipment.first?.requiredCertifications.isEmpty == true)
    }
}
