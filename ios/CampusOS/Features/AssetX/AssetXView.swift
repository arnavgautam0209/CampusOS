import SwiftUI

/// AssetX: live equipment stock, borrowing and returns. Faculty also see
/// everything currently out on loan or reported damaged/missing.
struct AssetXView: View {
    @EnvironmentObject private var inventory: InventoryStore
    @EnvironmentObject private var auth: AuthManager
    @EnvironmentObject private var skillPass: SkillPassStore
    @State private var borrowing: InventoryItem?
    @State private var returning: EquipmentLoan?
    @State private var showingSignIn = false

    private var isStaff: Bool { auth.currentUser?.role.isStaff == true }

    var body: some View {
        content
            .navigationTitle("AssetX")
            .task(id: "\(auth.isSignedIn)-\(isStaff)") {
                await inventory.load(signedIn: auth.isSignedIn, staff: isStaff)
                await skillPass.loadIfNeeded(signedIn: auth.isSignedIn)
            }
            .sheet(item: $borrowing) { item in
                NavigationStack { BorrowSheet(item: item) }
            }
            .sheet(item: $returning) { loan in
                NavigationStack { ReturnSheet(loan: loan) }
            }
            .sheet(isPresented: $showingSignIn) {
                NavigationStack { SignInView(showsCancel: true) }
            }
    }

    @ViewBuilder
    private var content: some View {
        if inventory.items.isEmpty, let message = inventory.loadState.errorMessage {
            ContentUnavailableView {
                Label("Can't Load Inventory", systemImage: "wifi.exclamationmark")
            } description: {
                Text(message)
            } actions: {
                Button("Try Again") { Task { await inventory.load(signedIn: auth.isSignedIn, staff: isStaff) } }
                    .buttonStyle(.borderedProminent)
            }
        } else if inventory.items.isEmpty, inventory.loadState != .loaded {
            ProgressView("Loading inventory…")
        } else {
            list
        }
    }

    private var list: some View {
        List {
            if let message = inventory.loadState.errorMessage {
                Label(message, systemImage: "exclamationmark.triangle.fill")
                    .font(.caption).foregroundStyle(.orange)
            }
            if !auth.isSignedIn {
                Section {
                    Button("Sign In to Borrow Equipment") { showingSignIn = true }
                }
            } else if !inventory.activeLoans.isEmpty {
                Section("Borrowed by You") {
                    ForEach(inventory.activeLoans) { loan in
                        LoanRow(loan: loan, showsBorrower: false) {
                            Button("Return") { returning = loan }
                                .buttonStyle(.bordered)
                        }
                    }
                }
            }
            if isStaff {
                Section {
                    if inventory.allLoans.isEmpty {
                        Text("Nothing is out on loan.").foregroundStyle(.secondary)
                    }
                    ForEach(inventory.allLoans) { loan in
                        LoanRow(loan: loan, showsBorrower: true) { EmptyView() }
                    }
                } header: {
                    Text("Out on Loan (All Students)")
                } footer: {
                    Text("Damaged or missing reports stay out of stock until staff mark them repaired or replaced in the admin site.")
                }
            }
            ForEach(inventory.itemsByLab, id: \.lab) { group in
                Section(group.lab) {
                    ForEach(group.items) { item in
                        InventoryItemRow(item: item, canBorrow: auth.isSignedIn) { borrowing = item }
                    }
                }
            }
        }
        .refreshable { await inventory.load(signedIn: auth.isSignedIn, staff: isStaff) }
    }
}

private struct InventoryItemRow: View {
    let item: InventoryItem
    let canBorrow: Bool
    let borrow: () -> Void
    @EnvironmentObject private var skillPass: SkillPassStore

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(alignment: .firstTextBaseline) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(item.name).font(.headline)
                    Text(item.category).font(.caption).foregroundStyle(.secondary)
                }
                Spacer()
                badge
            }
            Text(stockText)
                .font(.subheadline.monospacedDigit())
                .foregroundStyle(item.availableQuantity == 0 ? .red : .primary)
            if !item.requiredCertifications.isEmpty {
                let names = item.requiredCertifications.map { skillPass.certification(id: $0)?.name ?? $0 }
                let certified = item.requiredCertifications.allSatisfy { skillPass.standing(for: $0).isCertified }
                Label("Requires \(names.joined(separator: ", "))",
                      systemImage: certified ? "checkmark.seal.fill" : "lock.fill")
                    .font(.caption)
                    .foregroundStyle(certified ? .green : .secondary)
            }
            if item.isLoanable, canBorrow {
                Button("Borrow", action: borrow)
                    .buttonStyle(.borderedProminent)
                    .disabled(!item.canBorrow)
            }
        }
        .padding(.vertical, 4)
    }

    private var stockText: String {
        if item.underMaintenance { return "Under maintenance" }
        return "\(item.availableQuantity) of \(item.totalQuantity) available"
    }

    @ViewBuilder
    private var badge: some View {
        if item.underMaintenance {
            StatusBadge(text: "Maintenance", color: .red)
        } else if !item.isLoanable {
            StatusBadge(text: "Lab use only", color: .gray)
        } else if item.availableQuantity == 0 {
            StatusBadge(text: "Out of stock", color: .red)
        } else if item.isLowStock {
            StatusBadge(text: "Low stock", color: .orange)
        }
    }
}

private struct LoanRow<Action: View>: View {
    let loan: EquipmentLoan
    let showsBorrower: Bool
    @ViewBuilder let action: () -> Action

    var body: some View {
        HStack(alignment: .top) {
            VStack(alignment: .leading, spacing: 3) {
                Text("\(loan.equipmentName) × \(loan.quantity)").font(.headline)
                if showsBorrower {
                    Text("\(loan.borrower) (\(loan.username))").font(.subheadline)
                }
                Text(loan.labName).font(.caption).foregroundStyle(.secondary)
                if loan.status == .reported {
                    Text("Reported \(loan.condition): \(loan.note)")
                        .font(.caption).foregroundStyle(.red)
                } else {
                    Text("Due \(loan.dueAt.formatted(.relative(presentation: .named)))")
                        .font(.caption)
                        .foregroundStyle(loan.isOverdue ? .red : .secondary)
                }
            }
            Spacer()
            VStack(alignment: .trailing, spacing: 6) {
                if loan.isOverdue {
                    StatusBadge(text: "Overdue", color: .red)
                } else if loan.status == .reported {
                    StatusBadge(text: "Reported", color: .orange)
                }
                action()
            }
        }
        .padding(.vertical, 2)
    }
}
