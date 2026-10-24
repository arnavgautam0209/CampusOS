import SwiftUI

/// Borrow units of an item. The server re-checks stock and certifications.
struct BorrowSheet: View {
    let item: InventoryItem

    @EnvironmentObject private var inventory: InventoryStore
    @EnvironmentObject private var skillPass: SkillPassStore
    @Environment(\.dismiss) private var dismiss
    @State private var quantity = 1
    @State private var days = 1
    @State private var isSubmitting = false
    @State private var errorMessage: String?

    private static let loanLengths = [1, 3, 7, 14]
    private var maxQuantity: Int { max(1, min(item.availableQuantity, 10)) }

    var body: some View {
        Form {
            Section {
                LabeledContent("Item", value: item.name)
                LabeledContent("Lab", value: item.labName)
                LabeledContent("Available", value: "\(item.availableQuantity) of \(item.totalQuantity)")
            }
            Section("Loan") {
                Stepper("Quantity: \(quantity)", value: $quantity, in: 1...maxQuantity)
                Picker("Return within", selection: $days) {
                    ForEach(Self.loanLengths, id: \.self) { length in
                        Text(length == 1 ? "1 day" : "\(length) days").tag(length)
                    }
                }
            }
            if !item.requiredCertifications.isEmpty {
                Section {
                    ForEach(item.requiredCertifications, id: \.self) { id in
                        if let certification = skillPass.certification(id: id) {
                            CertificationRow(certification: certification, showsDescription: false)
                        } else {
                            Label(id, systemImage: "seal")
                        }
                    }
                } header: {
                    Text("Required Certification")
                } footer: {
                    Text("It must stay valid until you return the item.")
                }
            }
            if let errorMessage {
                Section {
                    Label(errorMessage, systemImage: "exclamationmark.triangle.fill")
                        .foregroundStyle(.red)
                }
            }
        }
        .navigationTitle("Borrow")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .cancellationAction) {
                Button("Cancel") { dismiss() }
            }
            ToolbarItem(placement: .confirmationAction) {
                if isSubmitting {
                    ProgressView()
                } else {
                    Button("Borrow") { Task { await submit() } }
                }
            }
        }
        .interactiveDismissDisabled(isSubmitting)
    }

    private func submit() async {
        isSubmitting = true
        defer { isSubmitting = false }
        errorMessage = nil
        do {
            try await inventory.borrow(item, quantity: quantity, days: days)
            dismiss()
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

/// Return a loan and say what condition it's in.
struct ReturnSheet: View {
    let loan: EquipmentLoan

    @EnvironmentObject private var inventory: InventoryStore
    @Environment(\.dismiss) private var dismiss
    @State private var condition = EquipmentLoan.Condition.ok
    @State private var note = ""
    @State private var isSubmitting = false
    @State private var errorMessage: String?

    private var needsNote: Bool { condition != .ok }
    private var canSubmit: Bool {
        !isSubmitting && (!needsNote || !note.trimmingCharacters(in: .whitespaces).isEmpty)
    }

    var body: some View {
        Form {
            Section {
                LabeledContent("Item", value: "\(loan.equipmentName) × \(loan.quantity)")
                LabeledContent("Lab", value: loan.labName)
            }
            Section {
                Picker("Condition", selection: $condition) {
                    ForEach(EquipmentLoan.Condition.allCases) { Text($0.label).tag($0) }
                }
                .pickerStyle(.segmented)
                if needsNote {
                    TextField("What happened?", text: $note, axis: .vertical)
                        .lineLimit(2...4)
                }
            } header: {
                Text("Condition")
            } footer: {
                if needsNote {
                    Text("Lab staff follow up on damaged or missing items. They stay out of stock until repaired or replaced.")
                }
            }
            if let errorMessage {
                Section {
                    Label(errorMessage, systemImage: "exclamationmark.triangle.fill")
                        .foregroundStyle(.red)
                }
            }
        }
        .navigationTitle("Return")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .cancellationAction) {
                Button("Cancel") { dismiss() }
            }
            ToolbarItem(placement: .confirmationAction) {
                if isSubmitting {
                    ProgressView()
                } else {
                    Button("Return") { Task { await submit() } }
                        .disabled(!canSubmit)
                }
            }
        }
        .interactiveDismissDisabled(isSubmitting)
    }

    private func submit() async {
        isSubmitting = true
        defer { isSubmitting = false }
        errorMessage = nil
        do {
            try await inventory.returnLoan(loan, condition: condition, note: note)
            dismiss()
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}
