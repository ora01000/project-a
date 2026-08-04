import axios from 'axios';
 
const apiClient = axios.create({
  baseURL: '/', // API Gateway 또는 서버의 기본 URL
  withCredentials: true, // HttpOnly 쿠키 포함 (Access Token 자동 전송)
});
 
// ...existing code...
 
// refresh 중복 호출 방지용 (동시에 401/403이 와도 refresh는 1번만)
let refreshInFlight = null;
let redirectingToLogin = false;
 
// 응답 인터셉터 추가 (Access Token 자동 갱신)
apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;
 
    // url에 Auth 포함시 인터셉터에서 제외
    if (originalRequest?.url?.includes(import.meta.env.VITE_URL_AUTH)) {
      return Promise.reject(error);
    }
 
    // 이미 재시도했는지 확인하는 플래그
    if (originalRequest?._retry) {
      return Promise.reject(error);
    }
 
    // 401 Unauthorized 또는 403 Forbidden 에러 발생 시
    if (error.response && (error.response.status === 401 || error.response.status === 403)) {
      originalRequest._retry = true; // 한 번만 재시도
 
      // refresh는 1개만 수행하고, 나머지는 같은 Promise를 기다리게 함
      if (!refreshInFlight) {
        refreshInFlight = refreshToken()
          .catch(() => false)
          .finally(() => {
            refreshInFlight = null;
          });
      }
 
      const refreshSuccess = await refreshInFlight;
 
      if (refreshSuccess) {
        return apiClient.request(originalRequest); // 원래 요청 재시도
      }
 
      // 실패 시 로그인으로 (여러 요청이 와도 1번만 이동)
      if (!redirectingToLogin) {
        redirectingToLogin = true;
        window.location.assign('/login');
      }
      return Promise.reject(error);
    }
 
    return Promise.reject(error);
  }
);
 
// Refresh Token 요청 함수
async function refreshToken() {
  try {
    const url = `${import.meta.env.VITE_URL_AUTH}/refresh`;
    await apiClient.post(url); // HttpOnly 쿠키 기반
    return true;
  } catch {
    return false;
  }
}
 
export default apiClient;
 
