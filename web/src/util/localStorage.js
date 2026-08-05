export const addUserToLocalStorage = (user) => {
    localStorage.setItem('user', JSON.stringify(user));
};

export const removeUserFromLocalStorage = () => {
    localStorage.removeItem('user');
};

export const getUserFromLocalStorage = () => {
    const result = localStorage.getItem('user');
    if (!result) {
        return null;
    }
    try {
        return JSON.parse(result);
    } catch {
        // Corrupt entry: treat it as logged out. This is read on every request
        // now that the axios interceptor pulls the token from here, so throwing
        // would take down every call rather than just the initial boot.
        localStorage.removeItem('user');
        return null;
    }
};