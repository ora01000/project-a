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

// °øðimport { useModal } from '../../../components/AppModal'
import { useCommonContext } from '../../../contexts/CommonProvider'
import { invokeAgent, getInvocationLatest, getInvocationInfo} from '../../../api/agentApi'
import { infoLog, warnLog, errorLog } from '../../../utils'
// Ç' ¸ðimport AgentTestSettingsModal from '../modals/AgentTestSettingsModal';

// »óconst MAX_ATTEMPTS = 60         // 2ºÐ2s * 60)
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
  // »çÀ dº¸ °¡n¿1â const { userState } = useCommonContext()
  const { user } = userState

  // ¸޽Ãöconst [messages, setMessages] = useState([
    { sender: 'agent', text: '¾ȳç¼¼¿ä¹«¾ùµ¿͵帱±î?' }
  ])

  // pending placeholder Àµ¦½º (¸»ǳ¼± ¾øºÇ³Ê¹®±¸¸¸)
  const pendingIdxRef = useRef(null)
  const abortRef = useRef(false)

  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)     // invoke ¿ä Á
  const [isPolling, setIsPolling] = useState(false) // °á Æ¸µ Á
  const [selectedTrace, setSelectedTrace] = useState(null)
  const [traceVisible, setTraceVisible] = useState(false)
  const [responseFormat, setResponseFormat] = useState('text')
  const [settings, setSettings] = useState({
    session_attributes: {},
    prompt_session_attributes: {},
    enable_trace: true,
  });
  // ·Ѹµ ¹®±¸
  const rollingTexts = [
    'ó¸®ÁÀ´ϴÙ',
    '°üº¸¸¦ °Ëä°íֽ4ϴÙ,
    '´õ: À´ä 'Ç ´õ·¡ »ýÂÁ',
    'v±ݸ¸ ±â·ÁÁ¼¼¿ä
  ]
  const [rollingTick, setRollingTick] = useState(0)

  // ===== ¼¼¼ÇID °ü===
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

  // ===== pending ±³ü/d¸® ÇÆ =====
  const replacePending = (payload) => {
    setMessages(prev => {
      const next = [...prev]
      const i = pendingIdxRef.current
      if (i == null || !next[i]) {
        // Àµ¦½º /½Ç´ë fail-safe
        return [...next, payload]
      }
      next[i] = payload            // ¡Úpending f°Å »õü¿£ pending ¾ø     return next
    })
    pendingIdxRef.current = null
    setMessages(prev => prev.filter(m => !m?.pending))
  }

  const cleanupAllPending = () => {
    setMessages(prev => prev.filter(m => !m?.pending))
    pendingIdxRef.current = null
  }

  // ===== °á Æ¸µ =====
  const startPollingForResult = async ({ agentId, sessionId }) => {
    setIsPolling(true)
    abortRef.current = false
    try {
      let attempts = 0
      while (attempts < MAX_ATTEMPTS) {
        attempts += 1
        if (abortRef.current) {
          infoLog('Æ¸µ Á´ܵÊ)
          replacePending({ sender: 'agent', text: 'À´äë¸¦ Ã¼Ò߽4ϴÙ' })
          return
        }
        const response = await getInvocationLatest(agentId, sessionId)
        const result = response.data
        // infoLog('Æ¸µ vȸ °á:', result)

        if (!result || !result?.agent_invocation_status) {
          await new Promise((r) => setTimeout(r, POLLING_INTERVAL))
          continue
        }

        // running/pendingÀ¸éè ´ë
        if (result?.agent_invocation_status === 'running' || result?.agent_invocation_status === 'pending') {
          await new Promise((r) => setTimeout(r, POLLING_INTERVAL))
          continue
        }

        // ¿ϷáÇÐµîÖ¾ »ó¡æóvȸ
        const detail = await getInvocationInfo(result?.agent_id, result?.agent_invocation_id)
        const info = detail.data
        infoLog('Æ¸µ À´ä, info)
        const finalText = info?.result?.text ?? 'ó¸® Á ¿7ù߻ýϴÙ'
        const finalTrace = info?.result?.trace

        replacePending({ sender: 'agent', text: finalText, trace: finalTrace })
        return
      }

      // ŸÀ¾ƿô°ú   replacePending({ sender: 'agent', text: 'À´äð£À Ã°ú½4ϴÙ À½ÃÈ¿¡ ´ٽÃ½õµÇ Á¼¼¿ä })
    } catch (e) {
      errorLog('°á Æ¸µ ½ÇÐ', e)
      replacePending({ sender: 'agent', text: 'ó¸® Á ¿7ù߻ýϴÙ À½ÃÈ¿¡ ´ٽÃ½õµÇ Á¼¼¿ä })
    } finally {
      setIsPolling(false)
    }
  }

  const handleStopPolling = () => {
    abortRef.current = true
    setIsPolling(false)
  }

  // ===== À¼Û=====
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

    // 1) »çÀ ¸޽Ãö  setMessages(prev => [...prev, { sender: 'user', text: input }])
    setInput('')

    // 2) ¿¡ÀÀƮ "´ë placeholder" (¸»ǳ¼± ¾ø·»´����­ ½ºÇ³Ê¹®±¸)
    if (pendingIdxRef.current == null) {
      setMessages(prev => {
        const next = [...prev, { sender: 'agent', pending: true }]
        pendingIdxRef.current = next.length - 1
        return next
      })
    }

    setLoading(true)

    try {
      // infoLog('Agent ȣÃ ÆÀ·εå, payload)
      const response = await invokeAgent(agentId, payload)
      const result = response.data
      infoLog('Á½ÃÀ´ä, result)
      // Á½ÃÀ´äælaceholder ±³ü
      replacePending({ sender: 'agent', text: result.text, trace: result.trace })
    } catch (error) {
      errorLog('À´äÇÐ', error)
      const status = error?.status || error?.response?.status
      if (status === 504) {
        // ŸÀ¾ƿô Æ¸µ ½ÃÛ(placeholder /Á)
        startPollingForResult({ agentId, sessionId })
      } else {
        const errorData = error?.response?.data
        const serverMessage = typeof errorData === 'string'? errorData : errorData?.message || errorData?.detail
        const errText = `¿7ù߻ýϴÙ- ${serverMessage || error?.message || 'Agent ½ÇàÇÐ ´ٽÃ½õµÇ¼¼¿ä}`
        replacePending({ sender: 'agent', text: errText })
      }
    } finally {
      setLoading(false)
    }
  }
  // »ý¿ë¸±â const handleTraceClick = (traceRawList) => {
    setSelectedTrace(traceRawList)
    setTraceVisible(true)
  }

  // ¼¼¼ÇÃ±â
  const handleRefresh = () => {
    setMessages([{ sender: 'agent', text: '¾ȳç¼¼¿ä¹«¾ùµ¿͵帱±î?' }])
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
      'Å½ºƮ ¼³d',
      'lg',
      () => {
        try {
          const parsed = settingsModalRef.current?.getParsedSettings()
          if (!parsed) return false
          setSettings(prev => ({ ...prev, ...parsed }))
          return true // true/undefined¸éð´Ýû     } catch {
          return false // °ËõÆ ½Ã¸ð/Á
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
          <COffcanvasTitle>Agent Å½ºƮ</COffcanvasTitle>
          <CButton className="ms-auto text-reset btn-close" onClick={onClose} aria-label="Close" />
        </COffcanvasHeader>
        <COffcanvasBody>
          <CCard style={{ margin: '10 auto', height: '80vh', display: 'flex', flexDirection: 'column' }}>
            <CCardHeader className="d-flex p-2 m-0">
              <CCol className="d-flex justify-content-start p-0 m-0" md={9}>
                <h6 style={{ margin: 0, display: 'block' }}>?? {agentName} ¿ÍÇ´ë</h6>
              </CCol>
              <CCol className="d-flex align-items-center justify-content-end p-0 m-0" md={3}>
                <CTooltip content={responseFormat === 'markdown' ? 'Å½ºƮ·Îº¸±â: 'Markdown8·Îº¸±â placement="bottom">
                  <CIcon
                    icon={responseFormat === 'markdown' ? cilDescription : cilText}
                    size="lg"
                    className={`me-3 ${responseFormat === 'markdown' ? 'text-primary' : ''}`}
                    style={{ display: 'block', cursor: 'pointer' }}
                    onClick={handleResponseFormatToggle}
                  />
                </CTooltip>
                <CTooltip content="¼¼¼ÇÃ±â" placement="bottom">
                  <CIcon icon={cilTrash} size="lg" className="me-3" style={{ display: 'block', cursor: 'pointer' }} onClick={handleRefresh} />
                </CTooltip>
                <CTooltip content="¼³d" placement="bottom">
                  <CIcon icon={cilSettings} size="lg" className="me-3" style={{ display: 'block', cursor: 'pointer' }} onClick={handleSettings} />
                </CTooltip>
              </CCol>
            </CCardHeader>

            <CCardBody className="d-flex flex-column" style={{ overflowY: 'auto', flex: 1 }}>
              <CListGroup className="flex-grow-1 overflow-auto">
                {messages.map((msg, idx) => {
                  const isUser = msg.sender === 'user'
                  const useMarkdown = !isUser && responseFormat === 'markdown'

                  // ¿¡ÀÀƮ ´ë placeholder: ¸»ǳ¼± ¾øºÇ³Ê+ ·Ѹµ ¹®±¸
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

                  // À¹Ý¹ö                  return (
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
                                  ?? »ý¿ë¸±â                               </a>
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
                                ?? »ý¿ë¸±â                             </a>
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
                  placeholder="¸޽ÃöÀ·Âϼ¼¿ä."
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
                  {isPolling ? 'ÁÁ' : (loading ? <CSpinner size="sm" /> : 'À¼Û)}
                </CButton>
              </div>
            </CCardBody>
          </CCard>
        </COffcanvasBody>
      </COffcanvas>

      {/* Trace View Offcanvas */}
      <COffcanvas placement="end" visible={traceVisible} onHide={() => setTraceVisible(false)} style={{ width: '30%', zIndex: 1100 }}>
        <COffcanvasHeader className="d-flex align-items-center">
          <COffcanvasTitle>?? ¿¡ÀÀƮÀ »ýOffcanvasTitle>
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

