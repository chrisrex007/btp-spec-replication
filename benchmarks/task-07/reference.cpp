#include <bits/stdc++.h>
using namespace std;
template <typename T, typename L>
inline bool smax(T &x, L y) {
  return x < y ? (x = y, true) : false;
}
template <typename T, typename L>
inline bool smin(T &x, L y) {
  return y < x ? (x = y, true) : false;
}
inline void build(int node, int b, int e);
inline long long query(int node, int b, int e, int l, int r);
inline void update(int node, int b, int e, int l, int r, int val);
inline void modify(int node, int b, int e, int l, int r, int val);
constexpr int MAXN = 1e5 + 15;
int n, q;
pair<long long, long long> tree[MAXN << 2];
long long a[MAXN];
int main() {
  ios_base::sync_with_stdio(false), cin.tie(NULL), cout.tie(NULL);
  cin >> n >> q;
  for (int i = 0; i < n; i++) cin >> a[i];
  build(1, 0, n);
  while (q--) {
    int type;
    cin >> type;
    if (type == 1) {
      int l, r;
      cin >> l >> r;
      cout << query(1, 0, n, l - 1, r) << '\n';
    } else if (type == 2) {
      int l, r, x;
      cin >> l >> r >> x;
      update(1, 0, n, l - 1, r, x);
    } else {
      int l, x;
      cin >> l >> x;
      modify(1, 0, n, l - 1, l, x);
    }
  }
  return false;
}
inline void build(int node, int b, int e) {
  if (b == e - 1) {
    tree[node] = make_pair(a[b], a[b]);
    return;
  }
  int mid = (b + e) >> 1;
  build(node << 1, b, mid);
  build(node << 1 | 1, mid, e);
  tree[node].first = tree[node << 1].first + tree[node << 1 | 1].first;
  tree[node].second = max(tree[node << 1].second, tree[node << 1 | 1].second);
}
inline long long query(int node, int b, int e, int l, int r) {
  if (b >= r || e <= l) {
    return 0;
  }
  if (b >= l && e <= r) {
    return tree[node].first;
  }
  int mid = (b + e) >> 1;
  return query(node << 1, b, mid, l, r) + query(node << 1 | 1, mid, e, l, r);
}
inline void update(int node, int b, int e, int l, int r, int val) {
  if (b >= r || e <= l || tree[node].second < val) {
    return;
  }
  if (b == e - 1) {
    tree[node].first %= val;
    tree[node].second = tree[node].first;
    return;
  }
  int mid = (b + e) >> 1;
  update(node << 1, b, mid, l, r, val);
  update(node << 1 | 1, mid, e, l, r, val);
  tree[node].first = tree[node << 1].first + tree[node << 1 | 1].first;
  tree[node].second = max(tree[node << 1].second, tree[node << 1 | 1].second);
}
inline void modify(int node, int b, int e, int l, int r, int val) {
  if (b >= r || e <= l) {
    return;
  }
  if (b >= l && e <= r) {
    tree[node].first = tree[node].second = val;
    return;
  }
  int mid = (b + e) >> 1;
  modify(node << 1, b, mid, l, r, val);
  modify(node << 1 | 1, mid, e, l, r, val);
  tree[node].first = tree[node << 1].first + tree[node << 1 | 1].first;
  tree[node].second = max(tree[node << 1].second, tree[node << 1 | 1].second);
}
