import Foundation
import Testing
@testable import CampusOS

/// A real response from POST /api/v1/ai/planner/ (keyword engine, hackathon example prompt).
let plannerFixtureJSON = #"""
{
 "engine": "keywords",
 "notes": [],
 "requirements": {
  "summary": "We are four students building a line-following robot. We need a robotics lab, Arduino boards, motors, IR sensors, soldering equipment, and two hours tomorrow.",
  "teamSize": 4,
  "date": "2026-10-25",
  "startTime": null,
  "durationMinutes": 120,
  "labType": "robotics",
  "items": [
   {
    "name": "Soldering Station",
    "quantity": null,
    "status": "available",
    "matches": [
     {
      "id": "EQ003",
      "name": "Soldering Station",
      "labId": "LAB001",
      "labName": "Robotics Lab",
      "isAvailable": true
     }
    ]
   },
   {
    "name": "Arduino Uno Boards",
    "quantity": null,
    "status": "available",
    "matches": [
     {
      "id": "EQ008",
      "name": "Arduino Uno Boards",
      "labId": "LAB001",
      "labName": "Robotics Lab",
      "isAvailable": true
     }
    ]
   },
   {
    "name": "DC Gear Motors",
    "quantity": null,
    "status": "available",
    "matches": [
     {
      "id": "EQ009",
      "name": "DC Gear Motors",
      "labId": "LAB001",
      "labName": "Robotics Lab",
      "isAvailable": true
     }
    ]
   }
  ]
 },
 "recommendations": [
  {
   "lab": {
    "id": "LAB001",
    "name": "Robotics Lab",
    "location": "Block A · 204",
    "symbol": "cpu",
    "capacity": 30,
    "equipment": [
     {
      "id": "EQ001",
      "name": "ESP32 Kits",
      "category": "Embedded",
      "isAvailable": true,
      "requiredCertifications": []
     },
     {
      "id": "EQ002",
      "name": "Robotic Arm",
      "category": "Robotics",
      "isAvailable": true,
      "requiredCertifications": [
       "CERT-ROBOT-ARM"
      ]
     },
     {
      "id": "EQ003",
      "name": "Soldering Station",
      "category": "Tools",
      "isAvailable": true,
      "requiredCertifications": [
       "CERT-SOLDER"
      ]
     },
     {
      "id": "EQ008",
      "name": "Arduino Uno Boards",
      "category": "Embedded",
      "isAvailable": true,
      "requiredCertifications": []
     },
     {
      "id": "EQ009",
      "name": "DC Gear Motors",
      "category": "Components",
      "isAvailable": true,
      "requiredCertifications": []
     }
    ],
    "isOpenForBooking": true,
    "requiredCertifications": []
   },
   "matchedEquipment": [
    {
     "id": "EQ003",
     "name": "Soldering Station",
     "isAvailable": true
    },
    {
     "id": "EQ008",
     "name": "Arduino Uno Boards",
     "isAvailable": true
    },
    {
     "id": "EQ009",
     "name": "DC Gear Motors",
     "isAvailable": true
    }
   ],
   "capacityOk": true,
   "canBook": true,
   "blockers": [],
   "certifications": [
    {
     "id": "CERT-SOLDER",
     "name": "Soldering Station Training",
     "status": "not_requested",
     "isValid": false,
     "requiredFor": "equipment",
     "equipment": "Soldering Station"
    }
   ],
   "slotsDate": "2026-10-25",
   "suggestedSlots": [
    {
     "start": "2026-10-25T09:00:00+05:30",
     "end": "2026-10-25T11:00:00+05:30"
    },
    {
     "start": "2026-10-25T09:30:00+05:30",
     "end": "2026-10-25T11:30:00+05:30"
    },
    {
     "start": "2026-10-25T10:00:00+05:30",
     "end": "2026-10-25T12:00:00+05:30"
    }
   ]
  }
 ],
 "missingItems": [],
 "nextSteps": [
  "Request Soldering Station Training training before using the Soldering Station.",
  "Reserve Robotics Lab on Sun 25 Oct at 09:00 for 120 minutes."
 ],
 "disclaimer": "CampusOS AI suggests a plan. Lab availability, bookings and certifications are checked by CampusOS when you act on it, and only faculty can approve training."
}
"""#

func plannerFixture() throws -> ProjectPlan {
    try JSONDecoder.campusOS.decode(ProjectPlan.self, from: Data(plannerFixtureJSON.utf8))
}

final class FakePlannerService: PlannerService {
    var results: [Result<ProjectPlan, Error>] = []
    private(set) var prompts: [String] = []

    func plan(prompt: String) async throws -> ProjectPlan {
        prompts.append(prompt)
        return try (results.count > 1 ? results.removeFirst() : results[0]).get()
    }
}

@Suite("Planner decoding")
struct PlannerDecodingTests {
    @Test func decodesRealServerPlan() throws {
        let plan = try plannerFixture()
        #expect(plan.engine == .keywords)
        #expect(plan.requirements.teamSize == 4)
        #expect(plan.requirements.durationMinutes == 120)
        #expect(plan.requirements.day != nil)
        #expect(plan.requirements.items.allSatisfy { $0.status == .available })

        let best = try #require(plan.recommendations.first)
        #expect(best.lab.id == "LAB001")
        #expect(best.canBook)
        #expect(best.lab.requiredCertifications.isEmpty)
        let slot = try #require(best.suggestedSlots.first)
        #expect(slot.minutes == 120)
        #expect(best.certifications.contains { $0.id == "CERT-SOLDER" && $0.requiredFor == "equipment" })
        #expect(!plan.nextSteps.isEmpty)
        #expect(!plan.disclaimer.isEmpty)
    }

    @Test func unknownEngineAndItemStatusDecodeAsOther() throws {
        let item = #"{"name":"Laser","quantity":2,"status":"on_order","matches":[]}"#
        #expect(try JSONDecoder.campusOS.decode(PlannedItem.self, from: Data(item.utf8)).status == .other)
        #expect(try JSONDecoder.campusOS.decode([PlannerEngine].self, from: Data(#"["gpt"]"#.utf8)) == [.other])
    }
}

@MainActor
@Suite("PlannerStore")
struct PlannerStoreTests {
    private let service = FakePlannerService()

    @Test func makePlanTrimsPromptAndStoresPlan() async throws {
        service.results = [.success(try plannerFixture())]
        let store = PlannerStore(service: service)

        await store.makePlan(prompt: "  build a robot \n")

        #expect(service.prompts == ["build a robot"])
        #expect(store.plan?.recommendations.first?.lab.id == "LAB001")
        #expect(store.loadState == .loaded)
        #expect(store.lastPrompt == "build a robot")
    }

    @Test func emptyPromptDoesNothing() async {
        let store = PlannerStore(service: service)
        await store.makePlan(prompt: "   ")
        #expect(service.prompts.isEmpty)
        #expect(store.loadState == .idle)
    }

    @Test func failureKeepsPreviousPlan() async throws {
        service.results = [.success(try plannerFixture()), .failure(APIError.unreachable)]
        let store = PlannerStore(service: service)
        await store.makePlan(prompt: "robot")
        await store.makePlan(prompt: "robot again")

        #expect(store.plan != nil)
        #expect(store.loadState.errorMessage == APIError.unreachable.localizedDescription)
    }

    @Test func refreshRerunsLastPromptAndClearsBookedSlots() async throws {
        let plan = try plannerFixture()
        service.results = [.success(plan)]
        let store = PlannerStore(service: service)
        await store.makePlan(prompt: "robot")
        let slot = try #require(plan.recommendations.first?.suggestedSlots.first)
        store.markBooked(slot)
        #expect(store.bookedSlots.contains(slot))

        await store.refresh()

        #expect(service.prompts == ["robot", "robot"])
        #expect(store.bookedSlots.isEmpty)
    }

    @Test func resetForgetsPlan() async throws {
        service.results = [.success(try plannerFixture())]
        let store = PlannerStore(service: service)
        await store.makePlan(prompt: "robot")
        store.reset()
        #expect(store.plan == nil)
        #expect(store.lastPrompt == nil)
        #expect(store.loadState == .idle)
    }

    @Test func bookingAPlannedSlotGoesThroughBookingStore() async throws {
        // The plan never books by itself: reserving a slot uses BookingStore,
        // which applies the usual checks and lets the server decide.
        let plan = try plannerFixture()
        let recommendation = try #require(plan.recommendations.first)
        let slot = try #require(recommendation.suggestedSlots.first)
        let bookings = FakeBookingService()
        let store = BookingStore(service: bookings, now: { slot.start.addingTimeInterval(-3600) })

        try await store.reserve(lab: recommendation.lab, start: slot.start, durationMinutes: slot.minutes)

        #expect(bookings.createCalls.first?.labID == "LAB001")
        #expect(bookings.createCalls.first?.durationMinutes == 120)
    }
}
