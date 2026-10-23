import Foundation
import Combine

protocol PlannerService {
    func plan(prompt: String) async throws -> ProjectPlan
}

struct APIPlannerService: PlannerService {
    let api: APIClient
    /// Claude can take several seconds; the server falls back to keywords well before this.
    static let timeout: TimeInterval = 60

    func plan(prompt: String) async throws -> ProjectPlan {
        struct Request: Encodable { let prompt: String }
        return try await api.post("ai/planner/", body: Request(prompt: prompt), authenticated: true,
                                  timeout: APIPlannerService.timeout)
    }
}

/// The latest AI plan. Acting on it (booking, requesting training) goes
/// through BookingStore and SkillPassStore, which the server checks again.
@MainActor
final class PlannerStore: ObservableObject {
    static let examplePrompt = "We are four students building a line-following robot. We need a robotics lab, "
        + "Arduino boards, motors, IR sensors, soldering equipment, and two hours tomorrow."

    @Published private(set) var plan: ProjectPlan?
    @Published private(set) var loadState: LoadState = .idle
    @Published private(set) var lastPrompt: String?
    /// Slots booked from this plan, so the UI can mark them.
    @Published private(set) var bookedSlots: Set<PlanSlot> = []

    private let service: PlannerService

    init(service: PlannerService) {
        self.service = service
    }

    func makePlan(prompt: String) async {
        let trimmed = prompt.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty, !loadState.isLoading else { return }
        loadState = .loading
        lastPrompt = trimmed
        do {
            plan = try await service.plan(prompt: trimmed)
            bookedSlots = []
            loadState = .loaded
        } catch {
            // Keep the previous plan visible; show why this one failed.
            loadState = .failed(error.localizedDescription)
        }
    }

    /// Re-runs the last prompt, e.g. after requesting training or booking.
    func refresh() async {
        guard let lastPrompt else { return }
        await makePlan(prompt: lastPrompt)
    }

    func markBooked(_ slot: PlanSlot) {
        bookedSlots.insert(slot)
    }

    func reset() {
        plan = nil
        lastPrompt = nil
        bookedSlots = []
        loadState = .idle
    }
}
