
#include <math.h>
#include <float.h>

void batch_dtw_sakoe_chiba(
    const float* target, int n,
    const float* windows, int num_windows,
    int w,
    float* out_distances
) {
    float dtw[160][160];
    if (n > 150) n = 150;
    
    for (int win = 0; win < num_windows; win++) {
        const float* win_ptr = windows + (win * n);
        
        for (int i = 0; i <= n; i++) {
            for (int j = 0; j <= n; j++) {
                dtw[i][j] = 1e9f;
            }
        }
        dtw[0][0] = 0.0f;
        
        for (int i = 1; i <= n; i++) {
            int j_start = (i - w > 1) ? i - w : 1;
            int j_end = (i + w + 1 < n + 1) ? i + w + 1 : n + 1;
            for (int j = j_start; j < j_end; j++) {
                float diff = target[i-1] - win_ptr[j-1];
                float cost = diff * diff;
                float m1 = dtw[i-1][j];
                float m2 = dtw[i][j-1];
                float m3 = dtw[i-1][j-1];
                float min_m = (m1 < m2) ? ((m1 < m3) ? m1 : m3) : ((m2 < m3) ? m2 : m3);
                dtw[i][j] = cost + min_m;
            }
        }
        out_distances[win] = sqrtf(dtw[n][n] / (float)n);
    }
}
