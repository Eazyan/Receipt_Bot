# Receipt Manager - Telegram Mini App Frontend

Beautiful and user-friendly Telegram Mini App for expense splitting.

## Features

-  Photo receipt recognition (AI-powered)
-  Invite friends via code or link
-  Item selection with counters
-  Automatic split calculation with tax and tip
-  Clean, mobile-first UI
-  Fast and responsive

## Tech Stack

- **React 18** - UI framework
- **TypeScript** - Type-safe development
- **Vite** - Ultra-fast build tool
- **Zustand** - Lightweight state management
- **Telegram Web App API** - Native integration

## Getting Started

### Prerequisites

- Node.js 16+ and npm/yarn
- Telegram Bot Token (for testing)

### Installation

```bash
npm install
```

### Development

```bash
npm run dev
```

The app will be available at `http://localhost:5173`

### Build

```bash
npm run build
```

Compiled files go to `dist/`

## Project Structure

```
src/
├── components/       # Reusable UI components
├── pages/           # Page components
├── hooks/           # Custom React hooks & state
├── utils/           # Helper functions (API, Telegram, format)
├── types/           # TypeScript type definitions
├── styles/          # Theme and global styles
├── App.tsx          # Main app component
└── main.tsx         # Entry point
```

## API Integration

The app communicates with the backend API. Configure the API URL in `.env`:

```
VITE_API_URL=http://localhost:8000/api
```

## User Flow

1. **Home Page** - Choose to create or join a room
2. **Create Room** - Upload receipt photo → Review → Share code
3. **Join Room** - Enter code → Select items → View results
4. **Results** - See split payments for all participants

## Styling

All styles are inline using the theme definitions in `src/styles/theme.ts`. No CSS files are used to keep the bundle minimal.

### Colors & Spacing

```typescript
colors.primary        // #0088cc
colors.success        // #31a24c
colors.error          // #ff453a
spacing.md            // 12px
borderRadius.md       // 12px
```

## Responsive Design

The UI is fully responsive and optimized for:
- Mobile phones (iOS & Android)
- Tablets
- Desktop browsers

Safe area padding is automatically handled for notched devices via `viewport-fit=cover`.

## Telegram Web App Integration

The app uses Telegram's Native API for:
- User authentication
- Haptic feedback
- Toast notifications
- Theme synchronization

See `src/utils/telegram.ts` for available functions.

## Performance

- Minimal dependencies (only React, Zustand, Axios)
- No runtime CSS-in-JS
- Optimized bundle size (~50KB gzipped)
- Fast image handling via Telegram's upload

## Testing

Currently no test setup. To add tests:

```bash
npm install -D vitest @testing-library/react
```

## Troubleshooting

### App not loading in Telegram
- Ensure `public/index.html` is served correctly
- Check browser console for errors
- Verify Telegram Web App API is loaded

### API requests failing
- Check `VITE_API_URL` in `.env`
- Ensure backend is running
- Verify CORS headers are set correctly

### Styling issues
- Inspect inline styles with browser DevTools
- Check `src/styles/theme.ts` for color/spacing values
- Clear browser cache and refresh

## Contributing

When adding new features:
1. Keep components small and focused
2. Use TypeScript for type safety
3. Follow the existing style patterns
4. Test on mobile devices
5. Check dark mode compatibility (future)

## License

MIT
