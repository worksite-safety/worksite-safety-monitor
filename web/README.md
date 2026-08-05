# web — Worksite AI Guardian dashboard

React 18 single-page app, built with [Vite](https://vite.dev). Charts, the event
report grid and the video preview for the worksite safety monitor; it talks to
the `engine` REST API over JWT.

## Setup

```
npm install
cp .env.example .env      # then edit if the engine is not on localhost:8080
```

## Scripts

| command | what it does |
| --- | --- |
| `npm run dev` (or `npm start`) | dev server on <http://localhost:3000> |
| `npm run build` | production bundle into `build/` |
| `npm run preview` | serve the built bundle on :3000 |
| `npm test` | Vitest, single run |
| `npm run test:watch` | Vitest in watch mode |

## Configuration

One variable, `VITE_API_URL` (see `.env.example`) — the base URL of the engine
API. It backs both the axios client (`src/util/axios.js`) and the video preview
frames (`src/pages/VideoStream.jsx`). It defaults to `http://localhost:8080`
when unset. Only `VITE_`-prefixed variables reach client code, and everything
that does is inlined into the shipped bundle, so never put a secret in `.env`.

### The port is not arbitrary

The dev server is pinned to **3000** with `strictPort`, because the engine
matches CORS origins exactly (`app.cors.allowed-origins`, default
`http://localhost:3000`) and rejects `*` at startup, and it builds password
reset links from `app.frontend.base-url` (also :3000). Running the frontend on
another port means setting `APP_CORS_ALLOWED_ORIGINS` and `APP_FRONTEND_BASE_URL`
on the engine to match. `strictPort` makes a busy port fail loudly rather than
silently drift to another one and break CORS.

## Auth

The JWT lives in `localStorage` under `user` (`src/util/localStorage.js`) and is
rehydrated into Redux as `userSlice`'s initial state. A **request interceptor**
in `src/util/axios.js` attaches `Authorization: Bearer …` to every call — call
sites do not spell the header out themselves. The response interceptor treats
any 403 as "session over": it clears storage and redirects to `/landing`. The
engine answers 403 for an expired, forged, or missing token.

## Layout

```
src/
  App.jsx            routes; the authenticated tree is gated on role === 'ADMIN'
  index.jsx          entry point
  store.js           Redux Toolkit store (one slice: user)
  features/user/     userSlice + thunks
  pages/             one file per route
  components/        shared UI; charts are recharts
  assets/wrappers/   styled-components, one wrapper per page/component
  util/              axios client, localStorage, nav links
```

Files containing JSX use the `.jsx` extension — Vite only applies the JSX
transform to `.jsx`/`.tsx`.
