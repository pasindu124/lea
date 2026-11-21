import { createContext, useContext } from 'react'

// Shared app state: the "as of" date override, the loaded meta (AI on/off, assumptions) and the user's name.
export const AppContext = createContext({ asOf: '', meta: null, user: '' })
export const useApp = () => useContext(AppContext)
