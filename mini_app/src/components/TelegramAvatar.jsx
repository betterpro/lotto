function getInitials(name) {
  if (!name) return '?'
  return name.split(' ').map(w => w[0]).join('').toUpperCase().slice(0, 2)
}

export default function TelegramAvatar({ user, size = 40, style = {} }) {
  const name  = user?.full_name || user?.username || '?'
  const photo = user?.photo_url

  if (photo) {
    return (
      <img
        src={photo}
        alt={name}
        style={{
          width: size, height: size, borderRadius: '50%',
          objectFit: 'cover', flexShrink: 0,
          border: '.5px solid var(--hairline-2)',
          ...style,
        }}
      />
    )
  }

  return (
    <div style={{
      width: size, height: size, borderRadius: '50%', flexShrink: 0,
      background: 'linear-gradient(135deg, #2EA6FF, #1a6fad)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      fontSize: Math.round(size * 0.36), fontWeight: 700, color: '#fff',
      letterSpacing: '.5px', userSelect: 'none',
      ...style,
    }}>
      {getInitials(name)}
    </div>
  )
}
