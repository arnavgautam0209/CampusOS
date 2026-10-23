import SwiftUI

struct LabDetailView: View {
    let lab: Lab
    @EnvironmentObject private var skillPass: SkillPassStore
    @EnvironmentObject private var auth: AuthManager

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                Image(systemName: lab.symbol)
                    .font(.system(size: 54))
                    .foregroundStyle(.indigo)
                    .frame(maxWidth: .infinity, minHeight: 140)
                    .background(.indigo.opacity(0.09), in: RoundedRectangle(cornerRadius: 18))
                Text(lab.name).font(.largeTitle.bold())
                Label(lab.location, systemImage: "mappin.and.ellipse")
                    .foregroundStyle(.secondary)
                Label("Capacity: \(lab.capacity)", systemImage: "person.3")
                StatusBadge(text: lab.isOpenForBooking ? "Open for bookings" : "Currently closed",
                            color: lab.isOpenForBooking ? .green : .red)
                if !lab.requiredCertifications.isEmpty {
                    Divider()
                    requirements
                }
                Divider()
                Text("Equipment").font(.title2.bold())
                ForEach(lab.equipment) { item in
                    equipmentRow(item)
                }
                Divider()
                NavigationLink { LabBookingView(lab: lab) } label: {
                    Text("Reserve Laboratory")
                        .font(.headline)
                        .frame(maxWidth: .infinity)
                        .padding()
                }
                .buttonStyle(.borderedProminent)
                .disabled(!lab.isOpenForBooking)
            }
            .padding()
        }
        .navigationTitle("Lab Details")
        .navigationBarTitleDisplayMode(.inline)
        .task(id: auth.isSignedIn) { await skillPass.loadIfNeeded(signedIn: auth.isSignedIn) }
    }

    private var missingCertifications: [String] {
        lab.requiredCertifications.filter { !skillPass.standing(for: $0).isCertified }
    }

    @ViewBuilder
    private var requirements: some View {
        Text("SkillPass Requirements").font(.title2.bold())
        if auth.isSignedIn, skillPass.loadState == .loaded, !missingCertifications.isEmpty {
            Label("You need faculty-approved certification before you can book this lab.",
                  systemImage: "lock.fill")
                .font(.subheadline)
                .foregroundStyle(.orange)
        } else if !auth.isSignedIn {
            Text("Sign in to check your certifications.")
                .font(.subheadline).foregroundStyle(.secondary)
        }
        ForEach(lab.requiredCertifications, id: \.self) { id in
            if let certification = skillPass.certification(id: id) {
                CertificationRow(certification: certification, showsDescription: false)
                    .padding(12)
                    .background(Color(.secondarySystemBackground), in: RoundedRectangle(cornerRadius: 12))
            } else {
                // Catalogue not loaded yet (or unreachable): still show what's required.
                Label(id, systemImage: "seal").font(.headline)
            }
        }
        Text("The CampusOS server checks certifications when you reserve.")
            .font(.caption).foregroundStyle(.secondary)
    }

    private func equipmentRow(_ item: Equipment) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Image(systemName: item.isAvailable ? "checkmark.circle.fill" : "xmark.circle.fill")
                    .foregroundStyle(item.isAvailable ? .green : .red)
                Text(item.name)
                Spacer()
                Text(item.isAvailable ? "Available" : "Unavailable")
                    .font(.caption).foregroundStyle(.secondary)
            }
            if !item.requiredCertifications.isEmpty {
                let names = item.requiredCertifications.map { skillPass.certification(id: $0)?.name ?? $0 }
                let certified = auth.isSignedIn
                    && item.requiredCertifications.allSatisfy { skillPass.standing(for: $0).isCertified }
                Label("Requires \(names.joined(separator: ", "))",
                      systemImage: certified ? "checkmark.seal.fill" : "lock.fill")
                    .font(.caption)
                    .foregroundStyle(certified ? .green : .secondary)
                    .padding(.leading, 28)
            }
        }
    }
}
