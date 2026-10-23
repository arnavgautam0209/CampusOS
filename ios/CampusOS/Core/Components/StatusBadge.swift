import SwiftUI

struct StatusBadge: View {
    let text: String
    let available: Bool
    var body: some View {
        Text(text)
            .font(.caption.weight(.semibold))
            .foregroundStyle(available ? .green : .orange)
            .padding(.horizontal, 9)
            .padding(.vertical, 5)
            .background((available ? Color.green : Color.orange).opacity(0.1))
            .clipShape(Capsule())
    }
}
