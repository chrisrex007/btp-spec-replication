#include <bits/stdc++.h>
using namespace std;
long long int n, m, s;
long long int t[200000], p[1000001];
vector<pair<long long int, pair<long long int, long long int>>> v(200000);
vector<pair<long long int, long long int>> ans(200000);
long long int block(long long int x) { return x / s; }
bool cmp1(pair<long long int, pair<long long int, long long int>> a,
          pair<long long int, pair<long long int, long long int>> b) {
  if (block(a.second.first) != block(b.second.first))
    return block(a.second.first) < block(b.second.first);
  if (block(a.second.first) % 2 == 0)
    return a.second.second < b.second.second;
  else
    return b.second.second < a.second.second;
}
bool cmp2(pair<long long int, long long int> a,
          pair<long long int, long long int> b) {
  if (a.first < b.first)
    return 1;
  else
    return 0;
}
void solve() {
  long long int r(-1), l(0);
  long long int sum(0);
  for (long long int i = 0; i < m; i++) {
    while (r < v[i].second.second) {
      r++;
      sum += t[r] * (2 * p[t[r]] + 1);
      p[t[r]]++;
    }
    while (l > v[i].second.first) {
      l--;
      sum += t[l] * (2 * p[t[l]] + 1);
      p[t[l]]++;
    }
    while (r > v[i].second.second) {
      sum -= t[r] * (2 * p[t[r]] - 1);
      p[t[r]]--;
      r--;
    }
    while (l < v[i].second.first) {
      sum -= t[l] * (2 * p[t[l]] - 1);
      p[t[l]]--;
      l++;
    }
    ans[i].first = v[i].first;
    ans[i].second = sum;
  }
}
int main() {
  ios_base::sync_with_stdio(0);
  cin.tie(0);
  cout.tie(0);
  cin >> n >> m;
  for (long long int i = 0; i < n; i++) cin >> t[i];
  s = n / sqrt(m);
  if (s == 0) s++;
  for (long long int i = 0; i < m; i++) {
    v[i].first = i;
    cin >> v[i].second.first >> v[i].second.second;
    v[i].second.first--;
    v[i].second.second--;
  }
  sort(v.begin(), v.begin() + m, cmp1);
  memset(p, 0, sizeof(p));
  solve();
  sort(ans.begin(), ans.begin() + m, cmp2);
  for (long long int i = 0; i < m; i++) cout << ans[i].second << endl;
  return 0;
}
