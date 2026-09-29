import React, { useState, useEffect, useRef} from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

// coreui
import {
  CCard,
  CCardBody,
  CCardHeader,
  CCol,
  CButton,
  CCloseButton,
  CForm,
  CFormInput,
  CFormSelect,
  CFormLabel,
  CTooltip,
  CContainer,
  CSpinner,
  CFormTextarea,
  COffcanvas,
  COffcanvasHeader,
  COffcanvasBody,
  COffcanvasTitle,
  CListGroup,
  CListGroupItem,
  CFormCheck,
} from '@coreui/react'
import CIcon from '@coreui/icons-react'
import { cilDescription, cilSettings, cilText, cilTrash} from '@coreui/icons'

// 공통
import { useModal } from '../../../components/AppModal'
import { useCommonContext } from '../../../contexts/CommonProvider'
import { invokeAgent, getInvocationLatest, getInvocationInfo} from '../../../api/agentApi'
import { infoLog, warnLog, errorLog } from '../../../utils'
// 별도 모달
import AgentTestSettingsModal from '../modals/AgentTestSettingsModal';

// 상수
const MAX_ATTEMPTS = 60         // 2분(2s * 60)
const POLLING_INTERVAL = 3000
const ROLLING_INTERVAL = 5000

const markdownComponents = {
  pre: ({ node, ...props }) => (
    <pre
      {...props}
      className="p-2 bg-light border rounded"
      style={{
        whiteSpace: 'pre-wrap',
        overflowWrap: 'anywhere',
        wordBreak: 'break-word',
      }}
    />
  ),
  code: ({ inline, className, children, ...props }) => (
    <code
      {...props}
      className={className}
      style={{
        background: inline ? '#f1f3f5' : 'transparent',
        padding: inline ? '0.1rem 0.3rem' : 0,
        borderRadius: inline ? '4px' : 0,
        whiteSpace: inline ? 'normal' : 'inherit',
        overflowWrap: 'anywhere',
        wordBreak: 'break-word',
      }}
    >
      {children}
    </code>
  ),
  a: ({ node, ...props }) => (
    <a {...props} target="_blank" rel="noreferrer" />
  ),
  ul: ({ node, ...props }) => <ul {...props} style={{ paddingLeft: '1.25rem', marginBottom: '0.8rem' }} />,
  ol: ({ node, ...props }) => <ol {...props} style={{ paddingLeft: '1.25rem', marginBottom: '0.8rem' }} />,
  li: ({ node, ...props }) => <li {...props} style={{ marginBottom: '0.35rem' }} />,
  p: ({ node, ...props }) => <p {...props} style={{ marginBottom: '0.9rem' }} />,
  h1: ({ node, ...props }) => (
    <h1 {...props} style={{ fontSize: '1.6rem', marginBottom: '0.9rem' }} />
  ),
  h2: ({ node, ...props }) => (
    <h2 {...props} style={{ fontSize: '1.35rem', marginBottom: '0.8rem' }} />
  ),
  h3: ({ node, ...props }) => (
    <h3 {...props} style={{ fontSize: '1.15rem', marginBottom: '0.7rem' }} />
  ),
}

const AgentTestOffcanvas = ({ visible, onClose, serviceId, agentId, agentName }) => {

  const bottomRef = useRef(null)
  const { showModal } = useModal()
  const settingsModalRef = useRef(null)
  // 사용자 정보 가져오기
  const { userState } = useCommonContext()
  const { user } = userState

  // 메시지
  const [messages, setMessages] = useState([
    { sender: 'agent', text: '안녕하세요, 무엇을 도와드릴까요?' }
  ])

  // pending placeholder 텍스트 (말풍선 없는 스피너 문구만)
  const pendingIdxRef = useRef(null)
  const abortRef = useRef(false)

  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)     // invoke 요청 중
  const [isPolling, setIsPolling] = useState(false) // 응답 폴링 중
  const [selectedTrace, setSelectedTrace] = useState(null)
  const [traceVisible, setTraceVisible] = useState(false)
  const [responseFormat, setResponseFormat] = useState('text')
  const [settings, setSettings] = useState({
    session_attributes: {},
    prompt_session_attributes: {},
    enable_trace: true,
  });
  // 롤링 문구
  const rollingTexts = [
    '처리중입니다',
    '관련 정보를 검색하고 있습니다.',
    '조금 더: 응답을 조금 더 생각',
    '잠시만 기다려주세요',
  ]
  const [rollingTick, setRollingTick] = useState(0)

  // ===== 세션ID 관리 =====
  const getSessionId = () => {
    let sid = sessionStorage.getItem('session-id')
    if (!sid) sid = setNewSessionId()
    return sid
  }
  const setNewSessionId = () => {
    const sid = crypto.randomUUID?.() || `${Date.now()}-${Math.random().toString(36).slice(2)}`
    sessionStorage.setItem('session-id', sid)
    return sid
  }
  const sessionId = getSessionId()

  // ===== pending 교체/처리 헬퍼 =====
  const replacePending = (payload) => {
    setMessages(prev => {
      const next = [...prev]
      const i = pendingIdxRef.current
      if (i == null || !next[i]) {
        // 텍스트 /실패 fail-safe
        return [...next, payload]
      }
      next[i] = payload            // pending 교체, 새로운 pending 없음
      return next
    })
    pendingIdxRef.current = null
    setMessages(prev => prev.filter(m => !m?.pending))
  }

  const cleanupAllPending = () => {
    setMessages(prev => prev.filter(m => !m?.pending))
    pendingIdxRef.current = null
  }

  // ===== 응답 폴링 =====
  const startPollingForResult = async ({ agentId, sessionId }) => {
    setIsPolling(true)
    abortRef.current = false
    try {
      let attempts = 0
      while (attempts < MAX_ATTEMPTS) {
        attempts += 1
        if (abortRef.current) {
          infoLog('폴링 중단됨')
          replacePending({ sender: 'agent', text: '응답을 취소했습니다' })
          return
        }
        const response = await getInvocationLatest(agentId, sessionId)
        const result = response.data
        // infoLog('폴링 조회 결과:', result)

        if (!result || !result?.agent_invocation_status) {
          await new Promise((r) => setTimeout(r, POLLING_INTERVAL))
          continue
        }

        // running/pending이면 대기
        if (result?.agent_invocation_status === 'running' || result?.agent_invocation_status === 'pending') {
          await new Promise((r) => setTimeout(r, POLLING_INTERVAL))
          continue
        }

        // 완료됐을때 상세조회
        const detail = await getInvocationInfo(result?.agent_id, result?.agent_invocation_id)
        const info = detail.data
        infoLog('폴링 응답', info)
        const finalText = info?.result?.text ?? '처리 중 오류가 발생했습니다'
        const finalTrace = info?.result?.trace

        replacePending({ sender: 'agent', text: finalText, trace: finalTrace })
        return
      }

      // 타임아웃
      replacePending({ sender: 'agent', text: '응답시간이 초과했습니다. 잠시 후에 다시 시도해 주세요' })
    } catch (e) {
      errorLog('응답 폴링 실패', e)
      replacePending({ sender: 'agent', text: '처리 중 오류가 발생했습니다. 잠시 후에 다시 시도해 주세요' })
    } finally {
      setIsPolling(false)
    }
  }

  const handleStopPolling = () => {
    abortRef.current = true
    setIsPolling(false)
  }

  // ===== 전송 =====
  const handleSend = async () => {
    if (!input.trim() || loading || isPolling) return

    const payload = {
      service_id: serviceId,
      session_id: sessionId,
      session_attributes: settings.session_attributes,
      prompt_session_attributes: settings.prompt_session_attributes,
      text: input,
      enable_trace: settings.enable_trace,
    }

    // 1) 사용자 메시지
    setMessages(prev => [...prev, { sender: 'user', text: input }])
    setInput('')

    // 2) 에이전트 "대기 placeholder" (말풍선 없이 스피너 문구)
    if (pendingIdxRef.current == null) {
      setMessages(prev => {
        const next = [...prev, { sender: 'agent', pending: true }]
        pendingIdxRef.current = next.length - 1
        return next
      })
    }

    setLoading(true)

    try {
      // infoLog('Agent 호출 페이로드', payload)
      const response = await invokeAgent(agentId, payload)
      const result = response.data
      infoLog('즉시응답', result)
      // 즉시응답으로 placeholder 교체
      replacePending({ sender: 'agent', text: result.text, trace: result.trace })
    } catch (error) {
      errorLog('응답실패', error)
      const status = error?.status || error?.response?.status
      if (status === 504) {
        // 타임아웃 폴링 시작(placeholder 유지)
        startPollingForResult({ agentId, sessionId })
      } else {
        const errorData = error?.response?.data
        const serverMessage = typeof errorData === 'string'? errorData : errorData?.message || errorData?.detail
        const errText = `오류가 발생했습니다 - ${serverMessage || error?.message || 'Agent 실행실패, 다시 시도해주세요'}`
        replacePending({ sender: 'agent', text: errText })
      }
    } finally {
      setLoading(false)
    }
  }

  // 상세보기
  const handleTraceClick = (traceRawList) => {
    setSelectedTrace(traceRawList)
    setTraceVisible(true)
  }

  // 세션초기화
  const handleRefresh = () => {
    setMessages([{ sender: 'agent', text: '안녕하세요, 무엇을 도와드릴까요?' }])
    setInput('')
    setNewSessionId()
    cleanupAllPending()
  }

  const handleSettings = () => {
    showModal(
      () => (
        <AgentTestSettingsModal
          ref={settingsModalRef}
          userId={user?.user_id}
          agentId={agentId}
          sessionId={sessionId}
          settings={settings}
          onSettingsChange={(newSettings) => setSettings(newSettings)}
        />
      ),
      '테스트 설정',
      'lg',
      () => {
        try {
          const parsed = settingsModalRef.current?.getParsedSettings()
          if (!parsed) return false
          setSettings(prev => ({ ...prev, ...parsed }))
          return true // true/undefined면 저장
        } catch {
          return false // 검증 실패 시 모달 닫기 방지
        }
      },
    );
  }

  const handleResponseFormatToggle = () => {
    setResponseFormat((prev) => {
      const next = prev === 'markdown' ? 'text' : 'markdown'
      if (user?.user_id && agentId) {
        localStorage.setItem(`${user.user_id}:agent-test-response-format:${agentId}`, next)
      }
      return next
    })
  }

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading, isPolling, rollingTick])

  useEffect(() => {
    if (!loading && !isPolling) return
    const t = setInterval(() => setRollingTick((t) => (t + 1) % rollingTexts.length), ROLLING_INTERVAL)
    return () => clearInterval(t)
  }, [loading, isPolling])

  useEffect(() => {
    const storageKey = `${user?.user_id}:agent-test`;
    const storedData = localStorage.getItem(storageKey);

    if (storedData) {
      try {
        const parsedData = JSON.parse(storedData);
        const agentSettings = parsedData?.[agentId];
        if (agentSettings) {
          setSettings(agentSettings);
        }
      } catch (error) {
        errorLog('Failed to parse settings from localStorage:', error);
      }
    }
  }, [user?.user_id, agentId]);

  useEffect(() => {
    if (!user?.user_id || !agentId) return
    const storedFormat = localStorage.getItem(`${user.user_id}:agent-test-response-format:${agentId}`)
    setResponseFormat(storedFormat === 'markdown' ? 'markdown' : 'text')
  }, [user?.user_id, agentId])

  return (
    <>
      {/* Main Chat Panel */}
      <COffcanvas placement="end" visible={visible} onHide={onClose} style={{ width: '40%' }}>
        <COffcanvasHeader className="d-flex align-items-center">
          <COffcanvasTitle>Agent 테스트</COffcanvasTitle>
          <CButton className="ms-auto text-reset btn-close" onClick={onClose} aria-label="Close" />
        </COffcanvasHeader>
        <COffcanvasBody>
          <CCard style={{ margin: '10 auto', height: '80vh', display: 'flex', flexDirection: 'column' }}>
            <CCardHeader className="d-flex p-2 m-0">
              <CCol className="d-flex justify-content-start p-0 m-0" md={9}>
                <h6 style={{ margin: 0, display: 'block' }}>💬 {agentName} 와의 대화</h6>
              </CCol>
              <CCol className="d-flex align-items-center justify-content-end p-0 m-0" md={3}>
                <CTooltip content={responseFormat === 'markdown' ? '텍스트로 보기' : 'Markdown으로 보기'} placement="bottom">
                  <CIcon
                    icon={responseFormat === 'markdown' ? cilDescription : cilText}
                    size="lg"
                    className={`me-3 ${responseFormat === 'markdown' ? 'text-primary' : ''}`}
                    style={{ display: 'block', cursor: 'pointer' }}
                    onClick={handleResponseFormatToggle}
                  />
                </CTooltip>
                <CTooltip content="세션초기화" placement="bottom">
                  <CIcon icon={cilTrash} size="lg" className="me-3" style={{ display: 'block', cursor: 'pointer' }} onClick={handleRefresh} />
                </CTooltip>
                <CTooltip content="설정" placement="bottom">
                  <CIcon icon={cilSettings} size="lg" className="me-3" style={{ display: 'block', cursor: 'pointer' }} onClick={handleSettings} />
                </CTooltip>
              </CCol>
            </CCardHeader>

            <CCardBody className="d-flex flex-column" style={{ overflowY: 'auto', flex: 1 }}>
              <CListGroup className="flex-grow-1 overflow-auto">
                {messages.map((msg, idx) => {
                  const isUser = msg.sender === 'user'
                  const useMarkdown = !isUser && responseFormat === 'markdown'

                  // 에이전트 대기 placeholder: 말풍선 없이 + 롤링 문구
                  if (!isUser && msg.pending === true && (loading || isPolling)) {
                    return (
                      <div key={idx} className="d-flex justify-content-start my-1 px-2">
                        <div className="d-flex align-items-center text-muted small">
                          <CSpinner size="sm" className="me-2" />
                          {rollingTexts[rollingTick]}
                        </div>
                      </div>
                    )
                  }

                  // 일반 버블
                  return (
                    <CListGroupItem
                      key={idx}
                      className={`d-flex ${isUser ? 'justify-content-end' : (useMarkdown ? 'justify-content-center' : 'justify-content-start')}`}
                      style={{ border: 'none', wordBreak: 'break-word', whiteSpace: isUser || !useMarkdown ? 'pre-wrap' : 'normal', minWidth: 0 }}
                    >
                      {useMarkdown ? (
                        <div className="w-100 py-2 d-flex justify-content-center">
                          <div
                            className="w-100"
                            style={{
                              maxWidth: '96%',
                              whiteSpace: 'normal',
                              overflowWrap: 'anywhere',
                              textAlign: msg.align || 'left',
                              lineHeight: 1.7,
                            }}
                          >
                            <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
                              {msg.text}
                            </ReactMarkdown>
                            {msg.trace && (
                              <div>
                                <a
                                  href="#"
                                  onClick={(e) => { e.preventDefault(); handleTraceClick(msg.trace) }}
                                  style={{ fontSize: '0.85rem', display: 'inline-block', marginTop: '0.25rem' }}
                                >
                                  📋 상세보기
                                </a>
                              </div>
                            )}
                          </div>
                        </div>
                      ) : (
                        <div
                          className={`p-2 rounded ${isUser ? 'bg-primary text-white' : 'bg-light text-dark'}`}
                          style={{ maxWidth: '75%' }}
                        >
                          {msg.text}
                          {!isUser && msg.trace && (
                            <div>
                              <a
                                href="#"
                                onClick={(e) => { e.preventDefault(); handleTraceClick(msg.trace) }}
                                style={{ fontSize: '0.85rem', display: 'inline-block', marginTop: '0.25rem' }}
                              >
                                📋 상세보기
                              </a>
                            </div>
                          )}
                        </div>
                      )}
                    </CListGroupItem>
                  )
                })}
                <div ref={bottomRef} />
              </CListGroup>

              <div className="mt-3 d-flex" style={{ alignItems: 'flex-end' }}>
                <CFormTextarea
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onInput={(e) => {
                    e.target.style.height = 'auto'
                    e.target.style.height = `${e.target.scrollHeight}px`
                  }}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                      e.preventDefault()
                      handleSend()
                    }
                  }}
                  placeholder="메시지를 입력하세요."
                  disabled={loading || isPolling}
                  rows={1}
                  style={{ resize: 'none', overflow: 'hidden', flex: 1, maxHeight: '200px' }}
                />
                <CButton
                  color={isPolling ? "danger" : "primary"}
                  onClick={isPolling ? handleStopPolling : handleSend}
                  disabled={loading}
                  className="ms-2"
                  style={{ height: 'calc(2.5rem + 1px)', alignSelf: 'flex-end' }}
                >
                  {isPolling ? '중지' : (loading ? <CSpinner size="sm" /> : '전송')}
                </CButton>
              </div>
            </CCardBody>
          </CCard>
        </COffcanvasBody>
      </COffcanvas>

      {/* Trace View Offcanvas */}
      <COffcanvas placement="end" visible={traceVisible} onHide={() => setTraceVisible(false)} style={{ width: '30%', zIndex: 1100 }}>
        <COffcanvasHeader className="d-flex align-items-center">
          <COffcanvasTitle>📋 에이전트 상세</COffcanvasTitle>
          <CCloseButton className="ms-auto text-reset" onClick={() => setTraceVisible(false)} />
        </COffcanvasHeader>
        <COffcanvasBody>
          <CCard style={{ maxWidth: '600px', margin: '0 auto', height: '80vh', display: 'flex', flexDirection: 'column' }}>
            <CCardBody className="d-flex flex-column" style={{ overflowY: 'auto', flex: 1 }}>
              <pre style={{ whiteSpace: 'pre-wrap' }}>{selectedTrace}</pre>
            </CCardBody>
          </CCard>
        </COffcanvasBody>
      </COffcanvas>
    </>
  )
}

export default AgentTestOffcanvas
