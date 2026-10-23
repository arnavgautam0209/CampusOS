import SwiftUI

/// The plan's sections inside the planner Form: what was understood,
/// recommended labs with bookable slots, missing items and next steps.
struct PlanSections: View {
    let plan: ProjectPlan

    var body: some View {
        Section {
            EngineBadge(engine: plan.engine)
            if !plan.requirements.summary.isEmpty {
                Text(plan.requirements.summary)
            }
            RequirementsSummary(requirements: plan.requirements)
            ForEach(Array(plan.requirements.items.enumerated()), id: \.offset) { _, item in
                PlannedItemRow(item: item)
            }
            ForEach(plan.notes, id: \.self) { note in
                Label(note, systemImage: "info.circle")
                    .font(.caption).foregroundStyle(.orange)
            }
        } header: {
            Text("What I Understood")
        }

        if plan.recommendations.isEmpty {
            Section("Recommended Labs") {
                Text("No suitable lab found.").foregroundStyle(.secondary)
            }
        }
        ForEach(Array(plan.recommendations.enumerated()), id: \.element.id) { index, recommendation in
            RecommendationSection(recommendation: recommendation, rank: index + 1,
                                  durationMinutes: plan.requirements.durationMinutes)
        }

        if !plan.missingItems.isEmpty {
            Section("Missing Items") {
                ForEach(Array(plan.missingItems.enumerated()), id: \.offset) { _, item in
                    VStack(alignment: .leading, spacing: 2) {
                        Label(item.name, systemImage: "shippingbox.and.arrow.backward")
                            .foregroundStyle(.orange)
                        Text(item.reason).font(.caption).foregroundStyle(.secondary)
                    }
                }
            }
        }

        Section {
            ForEach(Array(plan.nextSteps.enumerated()), id: \.offset) { index, step in
                HStack(alignment: .firstTextBaseline, spacing: 10) {
                    Text("\(index + 1).").bold().foregroundStyle(.indigo)
                    Text(step)
                }
            }
        } header: {
            Text("Next Steps")
        } footer: {
            Text(plan.disclaimer)
        }
    }
}

private struct EngineBadge: View {
    let engine: PlannerEngine

    var body: some View {
        switch engine {
        case .claude:
            Label("Planned with Claude, checked against campus data", systemImage: "sparkles")
                .font(.caption).foregroundStyle(.indigo)
        default:
            Label("Keyword matching (AI unavailable), checked against campus data",
                  systemImage: "text.magnifyingglass")
                .font(.caption).foregroundStyle(.orange)
        }
    }
}

private struct RequirementsSummary: View {
    let requirements: PlanRequirements

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            if let team = requirements.teamSize {
                Label("\(team) \(team == 1 ? "person" : "people")", systemImage: "person.3")
            }
            Label(dateText, systemImage: "calendar")
            Label("\(requirements.durationMinutes) minutes", systemImage: "clock")
        }
        .font(.subheadline)
    }

    private var dateText: String {
        let day = requirements.day?.formatted(date: .complete, time: .omitted) ?? requirements.date
        return requirements.startTime.map { "\(day), around \($0)" } ?? day
    }
}

private struct PlannedItemRow: View {
    let item: PlannedItem

    var body: some View {
        HStack(alignment: .firstTextBaseline) {
            Image(systemName: symbol).foregroundStyle(color)
            VStack(alignment: .leading, spacing: 2) {
                Text(item.quantity.map { "\(item.name) ×\($0)" } ?? item.name)
                Text(detail).font(.caption).foregroundStyle(.secondary)
            }
        }
        .accessibilityElement(children: .combine)
    }

    private var symbol: String {
        switch item.status {
        case .available: return "checkmark.circle.fill"
        case .unavailable: return "exclamationmark.circle.fill"
        case .notInCatalog, .other: return "xmark.circle.fill"
        }
    }

    private var color: Color {
        switch item.status {
        case .available: return .green
        case .unavailable: return .orange
        case .notInCatalog, .other: return .red
        }
    }

    private var detail: String {
        if item.matches.isEmpty { return "Not in the campus inventory" }
        let places = item.matches.map { "\($0.name) · \($0.labName)\($0.isAvailable ? "" : " (unavailable)")" }
        return places.joined(separator: ", ")
    }
}

private struct RecommendationSection: View {
    let recommendation: LabRecommendation
    let rank: Int
    let durationMinutes: Int

    @EnvironmentObject private var skillPass: SkillPassStore
    @EnvironmentObject private var bookings: BookingStore
    @EnvironmentObject private var planner: PlannerStore
    @State private var slotToBook: PlanSlot?
    @State private var bookingSlot: PlanSlot?
    @State private var alertTitle = ""
    @State private var alertMessage: String?

    var body: some View {
        Section {
            NavigationLink { LabDetailView(lab: recommendation.lab) } label: {
                VStack(alignment: .leading, spacing: 4) {
                    Text(recommendation.lab.location).font(.subheadline)
                    Text("\(recommendation.lab.capacity) seats · "
                         + "\(recommendation.matchedEquipment.count) of your items here")
                        .font(.caption).foregroundStyle(.secondary)
                }
            }
            if !recommendation.matchedEquipment.isEmpty {
                Text(recommendation.matchedEquipment.map(\.name).joined(separator: ", "))
                    .font(.caption)
            }
            ForEach(recommendation.blockers, id: \.self) { blocker in
                Label(blocker, systemImage: "lock.fill")
                    .font(.subheadline).foregroundStyle(.red)
            }
            ForEach(recommendation.certifications, id: \.id) { cert in
                certificationRow(cert)
            }
            slots
        } header: {
            HStack {
                Text("\(rank). \(recommendation.lab.name)")
                Spacer()
                StatusBadge(text: recommendation.canBook ? "Bookable" : "Blocked",
                            color: recommendation.canBook ? .green : .red)
            }
        }
        .confirmationDialog(
            "Reserve \(recommendation.lab.name)?",
            isPresented: Binding(get: { slotToBook != nil }, set: { if !$0 { slotToBook = nil } }),
            titleVisibility: .visible,
            presenting: slotToBook
        ) { slot in
            Button("Reserve \(slotText(slot))") { Task { await book(slot) } }
        }
        .alert(alertTitle, isPresented: Binding(get: { alertMessage != nil }, set: { if !$0 { alertMessage = nil } })) {
            Button("OK", role: .cancel) {}
        } message: {
            Text(alertMessage ?? "")
        }
    }

    @ViewBuilder
    private func certificationRow(_ cert: PlanCertification) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(cert.requiredFor == "lab" ? "Required to book this lab"
                 : "Required to use the \(cert.equipment ?? "equipment")")
                .font(.caption).foregroundStyle(.secondary)
            if let certification = skillPass.certification(id: cert.id) {
                // Live standing from SkillPass, with the Request Training button.
                CertificationRow(certification: certification, showsDescription: false)
            } else {
                Label(cert.name, systemImage: cert.isValid ? "checkmark.seal.fill" : "seal")
            }
        }
    }

    @ViewBuilder
    private var slots: some View {
        if recommendation.canBook, !recommendation.suggestedSlots.isEmpty {
            VStack(alignment: .leading, spacing: 8) {
                Text("Free times").font(.caption).foregroundStyle(.secondary)
                ForEach(recommendation.suggestedSlots, id: \.self) { slot in
                    slotButton(slot)
                }
            }
            .padding(.vertical, 4)
        }
    }

    private func slotButton(_ slot: PlanSlot) -> some View {
        let booked = planner.bookedSlots.contains(slot)
        return Button {
            slotToBook = slot
        } label: {
            HStack {
                Image(systemName: booked ? "checkmark.circle.fill" : "calendar.badge.plus")
                Text(slotText(slot))
                Spacer()
                if bookingSlot == slot { ProgressView() }
            }
        }
        .buttonStyle(.bordered)
        .tint(booked ? .green : .indigo)
        .disabled(booked || bookingSlot != nil)
    }

    private func slotText(_ slot: PlanSlot) -> String {
        let day = slot.start.formatted(.dateTime.weekday(.abbreviated).day().month(.abbreviated))
        let start = slot.start.formatted(date: .omitted, time: .shortened)
        let end = slot.end.formatted(date: .omitted, time: .shortened)
        return "\(day), \(start)–\(end)"
    }

    private func book(_ slot: PlanSlot) async {
        bookingSlot = slot
        defer { bookingSlot = nil }
        do {
            try await bookings.reserve(lab: recommendation.lab, start: slot.start, durationMinutes: slot.minutes)
            planner.markBooked(slot)
            alertTitle = "Reservation Confirmed"
            alertMessage = "\(recommendation.lab.name), \(slotText(slot)). It's in your Bookings tab."
        } catch {
            alertTitle = "Booking Failed"
            alertMessage = error.localizedDescription
        }
    }
}
