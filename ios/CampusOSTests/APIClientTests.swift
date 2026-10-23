import Foundation
import Testing
@testable import CampusOS

/// Intercepts URLSession requests so tests never need a running server.
final class StubURLProtocol: URLProtocol {
    struct Stub {
        var status = 200
        var json = "{}"
        var error: URLError?
    }

    nonisolated(unsafe) static var stub = Stub()
    nonisolated(unsafe) static var requests: [URLRequest] = []
    nonisolated(unsafe) static var bodies: [Data] = []

    static func reset(_ stub: Stub = Stub()) {
        self.stub = stub
        requests = []
        bodies = []
    }

    static func makeSession() -> URLSession {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [StubURLProtocol.self]
        return URLSession(configuration: configuration)
    }

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        Self.requests.append(request)
        Self.bodies.append(Self.readBody(of: request))
        if let error = Self.stub.error {
            client?.urlProtocol(self, didFailWithError: error)
            return
        }
        let response = HTTPURLResponse(url: request.url!, statusCode: Self.stub.status,
                                       httpVersion: nil, headerFields: ["Content-Type": "application/json"])!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data(Self.stub.json.utf8))
        client?.urlProtocolDidFinishLoading(self)
    }

    override func stopLoading() {}

    private static func readBody(of request: URLRequest) -> Data {
        if let body = request.httpBody { return body }
        guard let stream = request.httpBodyStream else { return Data() }
        stream.open()
        defer { stream.close() }
        var data = Data()
        var buffer = [UInt8](repeating: 0, count: 4096)
        while stream.hasBytesAvailable {
            let count = stream.read(&buffer, maxLength: buffer.count)
            guard count > 0 else { break }
            data.append(buffer, count: count)
        }
        return data
    }
}

private let testBaseURL = URL(string: "http://campus.test/api/v1/")!

private let bookingJSON = """
{"id":"d808ae4a-b8e6-405b-9231-1ce929912a92","labID":"LAB001","labName":"Robotics Lab",
 "start":"2026-10-24T22:30:00+05:30","end":"2026-10-24T23:30:00+05:30",
 "status":"active","createdAt":"2026-10-23T23:11:17.747476+05:30"}
"""

// Shares StubURLProtocol's static state, so these suites must not run in parallel.
@Suite(.serialized)
struct NetworkTests {
    private func makeClient(token: String? = nil) -> APIClient {
        APIClient(session: StubURLProtocol.makeSession(),
                  tokenStore: InMemoryTokenStore(token: token),
                  baseURL: { testBaseURL })
    }

    // MARK: APIClient

    @Test func labsAreFetchedWithoutTokenAndDecoded() async throws {
        StubURLProtocol.reset(.init(json: """
        [{"id":"LAB001","name":"Robotics Lab","location":"Block A","symbol":"cpu","capacity":30,
          "equipment":[{"id":"EQ001","name":"ESP32 Kits","category":"Embedded","isAvailable":true}],
          "isOpenForBooking":true}]
        """))
        let client = makeClient(token: "secret")

        let labs: [Lab] = try await client.get("labs/", authenticated: false)

        #expect(labs.first?.id == "LAB001")
        #expect(labs.first?.equipment.first?.name == "ESP32 Kits")
        let request = try #require(StubURLProtocol.requests.first)
        #expect(request.url?.absoluteString == "http://campus.test/api/v1/labs/")
        #expect(request.value(forHTTPHeaderField: "Authorization") == nil)
    }

    @Test func bookingDecodesDjangoDatesIncludingMicroseconds() async throws {
        StubURLProtocol.reset(.init(json: bookingJSON))
        let client = makeClient(token: "abc123")

        let booking: LabBooking = try await client.get("bookings/x/", authenticated: true)

        #expect(booking.start == ISO8601DateFormatter().date(from: "2026-10-24T17:00:00Z"))
        #expect(booking.status == .active)
        #expect(StubURLProtocol.requests.first?.value(forHTTPHeaderField: "Authorization") == "Token abc123")
    }

    @Test func authenticatedRequestWithoutTokenFailsBeforeNetwork() async {
        StubURLProtocol.reset()
        let client = makeClient(token: nil)

        await #expect(throws: APIError.notSignedIn) {
            let _: [LabBooking] = try await client.get("bookings/", authenticated: true)
        }
        #expect(StubURLProtocol.requests.isEmpty)
    }

    @Test func createBookingSendsJSONBody() async throws {
        StubURLProtocol.reset(.init(status: 201, json: bookingJSON))
        let service = APIBookingService(api: makeClient(token: "abc"))
        let start = ISO8601DateFormatter().date(from: "2026-10-24T17:00:00Z")!

        _ = try await service.createBooking(labID: "LAB001", start: start, durationMinutes: 90)

        let request = try #require(StubURLProtocol.requests.first)
        #expect(request.httpMethod == "POST")
        #expect(request.value(forHTTPHeaderField: "Content-Type") == "application/json")
        let body = try #require(JSONSerialization.jsonObject(with: StubURLProtocol.bodies[0]) as? [String: Any])
        #expect(body["labID"] as? String == "LAB001")
        #expect(body["start"] as? String == "2026-10-24T17:00:00Z")
        #expect(body["durationMinutes"] as? Int == 90)
    }

    @Test func cancelUsesLowercaseUUIDPath() async throws {
        StubURLProtocol.reset(.init(json: bookingJSON))
        let service = APIBookingService(api: makeClient(token: "abc"))
        let id = UUID(uuidString: "D808AE4A-B8E6-405B-9231-1CE929912A92")!

        _ = try await service.cancelBooking(id: id)

        #expect(StubURLProtocol.requests.first?.url?.absoluteString
                == "http://campus.test/api/v1/bookings/d808ae4a-b8e6-405b-9231-1ce929912a92/cancel/")
    }

    @Test func conflictUsesServerDetailMessage() async {
        StubURLProtocol.reset(.init(status: 409, json: #"{"detail":"This lab already has an overlapping reservation."}"#))
        await #expect(throws: APIError.conflict("This lab already has an overlapping reservation.")) {
            let _: LabBooking = try await makeClient(token: "abc").post("bookings/", authenticated: true)
        }
    }

    @Test func validationErrorUsesFirstFieldMessage() async {
        StubURLProtocol.reset(.init(status: 400, json: #"{"start":["Choose a future start time."]}"#))
        await #expect(throws: APIError.invalid("Choose a future start time.")) {
            let _: LabBooking = try await makeClient(token: "abc").post("bookings/", authenticated: true)
        }
    }

    @Test func plannerRequestUsesLongTimeout() async throws {
        StubURLProtocol.reset(.init(json: plannerFixtureJSON))
        let service = APIPlannerService(api: makeClient(token: "abc"))

        let plan = try await service.plan(prompt: "robot")

        let request = try #require(StubURLProtocol.requests.first)
        #expect(request.url?.absoluteString == "http://campus.test/api/v1/ai/planner/")
        #expect(request.timeoutInterval == 60)
        let body = try #require(JSONSerialization.jsonObject(with: StubURLProtocol.bodies[0]) as? [String: Any])
        #expect(body["prompt"] as? String == "robot")
        #expect(plan.recommendations.first?.lab.id == "LAB001")
    }

    @Test func ordinaryRequestsKeepShortTimeout() async throws {
        StubURLProtocol.reset(.init(json: "[]"))
        let _: [Lab] = try await makeClient().get("labs/", authenticated: false)
        #expect(StubURLProtocol.requests.first?.timeoutInterval == 15)
    }

    @Test func missingCertificationShowsSkillPassMessage() async {
        StubURLProtocol.reset(.init(status: 403, json: """
        {"detail":"This lab requires certification: Basic Electronics Safety. Ask faculty to approve your training in SkillPass.",
         "missingCertifications":["CERT-ELEC-BASIC"]}
        """))
        await #expect(throws: APIError.invalid(
            "This lab requires certification: Basic Electronics Safety. Ask faculty to approve your training in SkillPass.")) {
            let _: LabBooking = try await makeClient(token: "abc").post("bookings/", authenticated: true)
        }
    }

    @Test func serverErrorWithoutJSONMapsToStatus() async {
        StubURLProtocol.reset(.init(status: 500, json: "<html>oops</html>"))
        await #expect(throws: APIError.server(500)) {
            let _: [Lab] = try await makeClient().get("labs/", authenticated: false)
        }
    }

    @Test func connectionFailureMapsToUnreachable() async {
        StubURLProtocol.reset(.init(error: URLError(.cannotConnectToHost)))
        await #expect(throws: APIError.unreachable) {
            let _: [Lab] = try await makeClient().get("labs/", authenticated: false)
        }
    }

    @Test func malformedJSONMapsToBadResponse() async {
        StubURLProtocol.reset(.init(json: #"{"unexpected":true}"#))
        await #expect(throws: APIError.badResponse) {
            let _: [Lab] = try await makeClient().get("labs/", authenticated: false)
        }
    }

    // MARK: AuthManager

    @MainActor
    @Test func signInStoresTokenAndLoadsProfile() async throws {
        let client = makeClient()
        let auth = AuthManager(api: client)
        #expect(!auth.isSignedIn)

        // Token response first, then /auth/me/: answer both with one stub that
        // contains the fields each decoder needs.
        StubURLProtocol.reset(.init(json: """
        {"token":"tok-1","id":"7","name":"Alice Rao","email":"alice@example.edu","role":"student"}
        """))
        try await auth.signIn(username: "alice", password: "pw")

        #expect(auth.isSignedIn)
        #expect(client.tokenStore.readToken() == "tok-1")
        #expect(auth.currentUser?.name == "Alice Rao")
        #expect(auth.currentUser?.role == .student)
        #expect(StubURLProtocol.requests.map { $0.url?.absoluteString }
                == ["http://campus.test/api/v1/auth/token/", "http://campus.test/api/v1/auth/me/"])
        #expect(StubURLProtocol.requests[0].value(forHTTPHeaderField: "Authorization") == nil)
    }

    @MainActor
    @Test func badCredentialsShowServerMessageAndStaySignedOut() async {
        let client = makeClient()
        let auth = AuthManager(api: client)
        StubURLProtocol.reset(.init(status: 400, json: #"{"non_field_errors":["Unable to log in with provided credentials."]}"#))

        await #expect(throws: APIError.invalid("Unable to log in with provided credentials.")) {
            try await auth.signIn(username: "alice", password: "wrong")
        }
        #expect(!auth.isSignedIn)
        #expect(client.tokenStore.readToken() == nil)
    }

    @MainActor
    @Test func rejectedTokenSignsUserOut() async {
        let client = makeClient(token: "revoked")
        let auth = AuthManager(api: client)
        #expect(auth.isSignedIn)
        StubURLProtocol.reset(.init(status: 401, json: #"{"detail":"Invalid token."}"#))

        await #expect(throws: APIError.unauthorized) {
            let _: [LabBooking] = try await client.get("bookings/", authenticated: true)
        }
        #expect(!auth.isSignedIn)
        #expect(client.tokenStore.readToken() == nil)
    }

    @MainActor
    @Test func signOutClearsTokenAndUser() {
        let client = makeClient(token: "tok")
        let auth = AuthManager(api: client)

        auth.signOut()

        #expect(!auth.isSignedIn)
        #expect(auth.currentUser == nil)
        #expect(client.tokenStore.readToken() == nil)
    }
}

@Suite("Helpers")
struct HelperTests {
    @Test(arguments: [
        ("http://127.0.0.1:8000/api/v1/", "http://127.0.0.1:8000/api/v1/"),
        ("192.168.1.20:8000", "http://192.168.1.20:8000/api/v1/"),
        ("http://192.168.1.20:8000", "http://192.168.1.20:8000/api/v1/"),
        ("https://campus.example.edu/api/v1", "https://campus.example.edu/api/v1/"),
        ("  http://localhost:8000/  ", "http://localhost:8000/api/v1/"),
    ])
    func serverAddressIsNormalized(input: String, expected: String) {
        #expect(AppConfig.normalizedBaseURL(input)?.absoluteString == expected)
    }

    @Test(arguments: ["", "   ", "ftp://campus.test", "http://"])
    func invalidServerAddressIsRejected(input: String) {
        #expect(AppConfig.normalizedBaseURL(input) == nil)
    }

    @Test func parsesDjangoDateFormats() throws {
        let whole = ISO8601Parsing.date(from: "2026-10-24T22:30:00+05:30")
        let micro = ISO8601Parsing.date(from: "2026-10-24T22:30:00.747476+05:30")
        let utc = ISO8601Parsing.date(from: "2026-10-24T17:00:00Z")
        #expect(whole != nil)
        #expect(whole == utc)
        let fraction = try #require(micro).timeIntervalSince(try #require(whole))
        #expect(abs(fraction - 0.747) < 0.0005)
        #expect(ISO8601Parsing.date(from: "not a date") == nil)
    }

    @Test func keychainTokenRoundTrip() throws {
        let store = KeychainTokenStore(service: "com.campusos.tests.\(UUID().uuidString)")
        defer { store.deleteToken() }
        #expect(store.readToken() == nil)

        try store.saveToken("first")
        try store.saveToken("second")
        #expect(store.readToken() == "second")

        store.deleteToken()
        #expect(store.readToken() == nil)
    }
}
