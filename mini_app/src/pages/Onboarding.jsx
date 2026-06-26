import { useState, useEffect } from 'react'
import { CheckIcon, ShieldIcon, ArrowDownIcon } from '../components/Icon.jsx'
import TelegramAvatar from '../components/TelegramAvatar.jsx'
import { api } from '../api.js'
import { LOGO_SRC } from '../brand.js'
import { isTelegram } from '../routes.js'

function Section({ title, children }) {
  return (
    <div className="ob-section">
      <div className="ob-section-label">
        <span className="ob-section-tag">{title}</span>
      </div>
      <div className="ob-section-body">{children}</div>
    </div>
  )
}

function Clause({ n, children }) {
  return (
    <div className="ob-clause">
      <span className="ob-clause-n">{n}</span>
      <div className="ob-clause-body">{children}</div>
    </div>
  )
}

function CheckRow({ checked, onChange, children }) {
  return (
    <label className={'ob-check' + (checked ? ' on' : '')} onClick={() => onChange(!checked)}>
      <span className={'ob-check-box' + (checked ? ' on' : '')}>
        {checked && <CheckIcon width={13} height={13} />}
      </span>
      <span className="ob-check-text">{children}</span>
    </label>
  )
}

function Field({ label, required, children, flex }) {
  return (
    <div className="col gap-4" style={{ flex: flex ? 1 : 'initial', minWidth: 0, marginBottom: 10 }}>
      <span style={{ fontSize: 12, color: 'var(--tx-2)', letterSpacing: '.3px', fontWeight: 600 }}>
        {label}{required && <span style={{ color: 'var(--danger)' }}> *</span>}
      </span>
      {children}
    </div>
  )
}

export default function Onboarding({ onAccept, group, trustee, inviteSlug, user }) {
  const [step, setStep] = useState(1)
  const [scrolled, setScrolled] = useState(false)
  const [preview, setPreview] = useState(group && trustee ? { group, trustee } : null)
  const [confirmLoading, setConfirmLoading] = useState(false)
  const [confirmError, setConfirmError] = useState(null)

  useEffect(() => {
    if (preview || !inviteSlug) return
    api.group.preview(inviteSlug)
      .then(setPreview)
      .catch(() => setConfirmError('Could not load group. Check your invite link.'))
  }, [inviteSlug, preview])

  const trusteeName = preview?.trustee?.full_name || preview?.trustee?.username || 'your trustee'
  const groupName = preview?.group?.name || 'this group'

  const [info, setInfo] = useState(() => ({
    fullName: '',
    email: (user?.email || user?.auth_email || '').trim().toLowerCase(),
    street: '', city: '', province: 'BC', postal: '', phone: '',
    age19: false, category: 'e',
  }))

  const upd = (k, v) => setInfo(prev => ({ ...prev, [k]: v }))

  const infoValid = info.fullName.trim() && info.street.trim() && info.city.trim() &&
    info.province && info.postal.trim() && info.phone.trim() &&
    /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(info.email.trim()) && info.age19

  const [agree, setAgree] = useState({ terms: false, privacy: false, accuracy: false })
  const allChecked = agree.terms && agree.privacy && agree.accuracy

  const onScroll = (e) => {
    const el = e.target
    if (el.scrollHeight - el.scrollTop - el.clientHeight < 30) setScrolled(true)
  }

  return (
    <div className="ob">
      <div className="ob-panel">
        <div className="ob-top">
          <div className="ob-top-brand">
            <img src={LOGO_SRC} alt="Lotto Chee" className="ob-top-logo" />
            <span className="ob-top-step">One-time setup · Step {step} of 3</span>
          </div>
          <div className="ob-steps">
            <span className={'dot' + (step >= 1 ? ' on' : '')} />
            <span className={'dash' + (step >= 2 ? ' on' : '')} />
            <span className={'dot' + (step >= 2 ? ' on' : '')} />
            <span className={'dash' + (step >= 3 ? ' on' : '')} />
            <span className={'dot' + (step >= 3 ? ' on' : '')} />
          </div>
        </div>

      {step === 1 && (
        <>
          <div className="ob-scroll">
            <div className="ob-intro ob-intro--center">
              <span className="ob-eyebrow">Confirm your group</span>
              <h2 className="ob-h2">Is this the right group?</h2>
              <p className="ob-p">
                You are joining <strong>{groupName}</strong>. Your trustee holds pooled tickets
                on behalf of the group.
              </p>
            </div>
            <div className="ob-confirm-card">
              <TelegramAvatar user={preview?.trustee || {}} size={72} />
              <span className="ob-confirm-name">{trusteeName}</span>
              <span className="ob-confirm-role">Group trustee · {groupName}</span>
            </div>
            {confirmError && (
              <p className="ob-error">{confirmError}</p>
            )}
          </div>
          <div className="ob-foot">
            <button
              className="btn btn-primary btn-block"
              disabled={confirmLoading || (!preview && !!inviteSlug)}
              onClick={async () => {
                setConfirmError(null)
                setConfirmLoading(true)
                try {
                  if (inviteSlug && !group) {
                    await api.group.join(inviteSlug)
                  }
                  setStep(2)
                } catch (e) {
                  setConfirmError(e.message || 'Could not join group')
                } finally {
                  setConfirmLoading(false)
                }
              }}
            >
              {confirmLoading ? 'Joining…' : `Yes — join ${groupName}`}
            </button>
          </div>
        </>
      )}

      {step === 2 && (
        <>
          <div className="ob-scroll">
            <div className="ob-intro">
              <span className="ob-eyebrow">Beneficiary information</span>
              <h2 className="ob-h2">Tell us who you are</h2>
              <p className="ob-p">
                Because Lotto Chee buys real BCLC group tickets on your behalf, we need to
                register you as a <strong>Beneficiary</strong>. Your details are required by
                the <strong>Group Prize Agreement</strong> if any pooled ticket wins $1,000 CAD or more.
              </p>
            </div>

            <Section title="Personal details">
              <Field label="Full legal name" required>
                <input className="input" value={info.fullName}
                  onChange={e => upd('fullName', e.target.value)} placeholder="Liam Park" />
              </Field>
              <Field label="Email used for e-Transfer" required>
                <input className="input mono" type="email" value={info.email}
                  onChange={e => upd('email', e.target.value.trim().toLowerCase())}
                  placeholder="you@example.com" />
              </Field>
              <Field label="Street address (include Unit #)" required>
                <input className="input" value={info.street}
                  onChange={e => upd('street', e.target.value)} placeholder="221 Howe St, #1402" />
              </Field>
              <div className="row gap-8">
                <Field label="City" required flex>
                  <input className="input" value={info.city}
                    onChange={e => upd('city', e.target.value)} placeholder="Vancouver" />
                </Field>
                <Field label="Province" required>
                  <select className="input" value={info.province}
                    onChange={e => upd('province', e.target.value)} style={{ width: 80 }}>
                    {['AB','BC','MB','NB','NL','NS','NT','NU','ON','PE','QC','SK','YT'].map(p =>
                      <option key={p} value={p}>{p}</option>)}
                  </select>
                </Field>
              </div>
              <div className="row gap-8">
                <Field label="Postal code" required flex>
                  <input className="input mono" value={info.postal}
                    onChange={e => upd('postal', e.target.value.toUpperCase())} placeholder="V6Z 2M3" />
                </Field>
                <Field label="Phone" required flex>
                  <input className="input mono" value={info.phone}
                    onChange={e => upd('phone', e.target.value)} placeholder="+1 604 555 0142" />
                </Field>
              </div>
            </Section>

            <Section title="Declaration & age">
              <p className="ob-p" style={{ fontSize: 13 }}>
                BCLC requires every beneficiary to be at least 19 and to declare any
                relationship to a lottery retailer or BCLC employee.
              </p>
              <CheckRow checked={info.age19} onChange={v => upd('age19', v)}>
                I confirm I am at least <strong>19 years of age</strong>.
              </CheckRow>
              <div className="ob-cat-label">I am a member of category:</div>
              <div className="ob-cat-list">
                {[
                  ['a', 'A Lottery Retailer (operates or works at a BCLC retail location)'],
                  ['b', 'A family member of a Lottery Retailer (parent, child, spouse, household)'],
                  ['c', 'A BCLC employee'],
                  ['d', 'A family member of a BCLC employee'],
                  ['e', 'None of the above'],
                ].map(([k, label]) => (
                  <label key={k} className={'ob-cat' + (info.category === k ? ' on' : '')}
                    onClick={() => upd('category', k)}>
                    <span className="ob-cat-key mono">{k.toUpperCase()}</span>
                    <span className="ob-cat-text">{label}</span>
                    {info.category === k && <CheckIcon width={15} height={15} style={{ color: 'var(--money)', flexShrink: 0 }} />}
                  </label>
                ))}
              </div>
              {info.category !== 'e' && (
                <div className="ob-warn">
                  <ShieldIcon width={14} height={14} style={{ flexShrink: 0 }} />
                  Categories a–d follow a different BCLC prize payout procedure for your share.
                </div>
              )}
            </Section>
          </div>

          <div className="ob-foot">
            <button className="btn btn-primary btn-block"
              disabled={!infoValid} style={{ opacity: infoValid ? 1 : .45 }}
              onClick={() => { setStep(3); setScrolled(false) }}>
              Continue to agreement
            </button>
            <div className="ob-foot-note">
              <ShieldIcon width={11} height={11} />
              Your info is stored only to register you as a beneficiary.
            </div>
          </div>
        </>
      )}

      {step === 3 && (
        <>
          <div className="ob-scroll" onScroll={onScroll}>
            <div className="ob-intro">
              <span className="ob-eyebrow">Legal · BCLC Group Prize Agreement</span>
              <h2 className="ob-h2">Group Prize Agreement</h2>
              <p className="ob-p">
                Agreement with your trustee <strong>{trusteeName}</strong> for {groupName}.
                Required when a pooled ticket wins <strong>$1,000 CAD or more</strong>.
              </p>
            </div>

            <Section title="Ticket information">
              <div className="ob-readout">
                <div><span style={{ fontSize: 13, color: 'var(--tx-2)' }}>Ticket name</span>
                  <span className="mono" style={{ fontSize: 13 }}>Lotto Max</span></div>
                <div><span style={{ fontSize: 13, color: 'var(--tx-2)' }}>Draw date(s)</span>
                  <span className="mono" style={{ fontSize: 13 }}>Each draw round you join</span></div>
                <div><span style={{ fontSize: 13, color: 'var(--tx-2)' }}>Ticket control number</span>
                  <span className="mono" style={{ fontSize: 13 }}>Auto-assigned per round</span></div>
              </div>
              <p className="ob-p" style={{ fontSize: 13 }}>
                <strong>{trusteeName}</strong> is your <strong>Group Trustee</strong> — they hold each
                pooled ticket on behalf of all beneficiaries who joined that round.
              </p>
            </Section>

            <Section title="Terms and conditions">
              <p className="ob-p" style={{ marginBottom: 12 }}>
                Each of the Beneficiaries, for and in consideration of and to induce the
                Corporations to make payment or deliver any and all prizes associated with the
                Ticket (the "Prize"), hereby represent and warrant to and agree with the
                Corporations as follows:
              </p>
              <Clause n={1}>That the Beneficiaries are the only individuals with a legal or beneficial
                interest in the <em>Lotto Max</em> ticket bearing the control number assigned by Lotto Chee
                for the round joined (the <strong>Ticket</strong>).</Clause>
              <Clause n={2}>The Group Trustee is the lawful holder of the Ticket and no person other than
                the Beneficiaries has any interest in the Ticket or any right to payment or delivery
                of any portion of the Prize.</Clause>
              <Clause n={3}>That <strong>{trusteeName}</strong> ("Group Trustee") has been authorized
                by the Beneficiaries to accept from BCLC, for and on behalf of all Beneficiaries, the Prize.</Clause>
              <Clause n={4}>That the Group Trustee is: (a) a Beneficiary and member of the group entitled to
                receive a share of the Prize; (b) the holder of the ticket as trustee for the Beneficiaries;
                and (c) irrevocably authorized to receive payment of the Prize from the Corporations in
                trust for the Beneficiaries.</Clause>
              <Clause n={5}>It is the responsibility of the Group Trustee and Beneficiaries, and not the
                Corporations, to ensure that the Prize is distributed to the Beneficiaries as the parties
                solely entitled to receive a portion of the Prize.</Clause>
              <Clause n={6}>The Beneficiaries have read, are familiar with and agree to be bound by, all rules
                and regulations, game conditions and prize structure statements adopted by the Corporations
                that apply to the Game or the Ticket.</Clause>
              <Clause n={7}>Payment or delivery of the Prize to the Group Trustee by the Corporations as directed
                herein releases the Corporations from any further claims or demands by any Beneficiary
                in respect of the Ticket.</Clause>
              <Clause n={8}>That the Beneficiaries agree the Ticket is not eligible for any additional payments
                or prizes even where payments or prizes on other tickets in the Game are unclaimed.</Clause>
              <Clause n={9}>All parties entitled to the Prize have been identified as a Beneficiary in this
                agreement. All Beneficiaries acknowledge that BCLC has no responsibility to ensure receipt
                of any Prize or portion thereof by any Beneficiary.</Clause>
              <Clause n={10}>The Beneficiaries are each the full age of <strong>nineteen (19) years</strong>.</Clause>
              <Clause n={11}>The Beneficiaries hereby authorize and consent to BCLC collecting, recording, publishing
                and broadcasting their respective names, addresses, places of residence, prize details,
                images and expressed statements (a) without any claim for licensing or broadcasting rights;
                and (b) without any claim related to the public release of the Beneficiaries' Information.</Clause>
              <Clause n={12}>After two years from the date BCLC first declares the Beneficiaries' win publicly, BCLC
                will, where feasible, remove or prevent further publication of the Beneficiaries' Information
                on BCLC-controlled media. BCLC cannot control use by third parties beyond the two-year period.</Clause>
              <Clause n={13}>The Beneficiaries hereby, jointly and severally, undertake to <strong>indemnify and
                save BCLC and the ILC harmless</strong> from and against any liability, actions, claims, demands,
                losses, payment and costs of any nature whatsoever related to the Ticket, the Prize, publication
                of the Beneficiaries' Information and the prize claim process.</Clause>
              <Clause n={14}>This Agreement may be executed in counter-parts by the Group Trustee and Beneficiaries
                and shall be binding upon the Group Trustee and Beneficiaries and their respective heirs,
                executors, administrators and assigns.</Clause>
              <Clause n={15}>That each Beneficiary has completed, in full, the information required above and by
                their signature below acknowledges he or she: (a) has read and accepts all terms contained herein;
                (b) has been given the opportunity to obtain independent legal advice; (c) confirms that all
                information provided is true and accurate.</Clause>
            </Section>

            <Section title="Privacy statement">
              <p className="ob-p">
                Your personal information is collected in accordance with the <em>Freedom of Information
                and Protection of Privacy Act</em>, British Columbia, and will be used by BCLC to administer
                and process lottery prizes (including verifying prize claims and fraud investigations); if you
                are a winner, publication of details for game integrity purposes; and to comply with applicable laws.
              </p>
              <p className="ob-p" style={{ fontSize: 13, color: 'var(--tx-3)' }}>
                Questions? Contact BCLC Customer Support at 74 West Seymour Street, Kamloops, BC V2C 1E2 · 1-866-815-0222 · bclc.com.
              </p>
            </Section>

            <Section title="Signatures & declarations">
              <div className="ob-sig">
                <div className="ob-sig-row">
                  <div className="col grow">
                    <span className="ob-eyebrow">Beneficiary signature</span>
                    <div className="ob-sig-box">
                      <span className="mono" style={{ color: 'var(--tg)' }}>{info.fullName || '—'}</span>
                      <span style={{ fontSize: 12, color: 'var(--tx-3)' }}>
                        Digitally signed{isTelegram() ? ' via Telegram' : ''} · {new Date().toLocaleDateString('en-CA')}
                      </span>
                    </div>
                  </div>
                  <div className="ob-sig-cat">
                    <span className="ob-eyebrow">Decl.</span>
                    <div className="ob-sig-cat-letters">
                      {['a','b','c','d','e'].map(k => (
                        <span key={k} className={'mono' + (info.category === k ? ' on' : '')}>{k}</span>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            </Section>

            <div className="ob-checks">
              <CheckRow checked={agree.terms} onChange={v => setAgree(a => ({ ...a, terms: v }))}>
                I have <strong>read and accept</strong> all terms contained in the Group Prize Agreement,
                and have been given the opportunity to obtain independent legal advice.
              </CheckRow>
              <CheckRow checked={agree.privacy} onChange={v => setAgree(a => ({ ...a, privacy: v }))}>
                I agree to BCLC's <strong>Privacy Statement</strong> and the use, access, disclosure and
                storage of my personal information inside and outside of Canada.
              </CheckRow>
              <CheckRow checked={agree.accuracy} onChange={v => setAgree(a => ({ ...a, accuracy: v }))}>
                I confirm all information I have provided is <strong>true and accurate</strong>,
                and that I am the only individual with a legal interest in any share I purchase.
              </CheckRow>
            </div>
          </div>

          <div className="ob-foot">
            {!scrolled && (
              <div className="ob-scroll-hint">
                <ArrowDownIcon width={12} height={12} /> Please scroll to the bottom to enable Agree
              </div>
            )}
            <div className="row gap-8">
              <button className="btn btn-ghost btn-sm" onClick={() => setStep(2)}>Back</button>
              <button className="btn btn-primary" style={{ flex: 1, opacity: scrolled && allChecked ? 1 : .45 }}
                disabled={!(scrolled && allChecked)}
                onClick={() => onAccept({ ...info, acceptedAt: new Date().toISOString() })}>
                <CheckIcon width={16} height={16} /> Agree &amp; start using Lotto Chee
              </button>
            </div>
          </div>
        </>
      )}
      </div>
    </div>
  )
}
