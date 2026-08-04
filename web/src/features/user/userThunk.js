import customFetch from '../../util/axios';

import {logoutUser} from './userSlice';

export const registerUserThunk = async (url, user, thunkAPI) => {
    try {
        const resp = await customFetch.post(url, user);
        return resp.data;
    } catch (error) {
        return thunkAPI.rejectWithValue(error.response.data.msg);
    }
};

export const loginUserThunk = async (url, user, thunkAPI) => {
    try {
        const resp = await customFetch.post(url, user);
        return resp.data;
    } catch (error) {
        return thunkAPI.rejectWithValue(error.response.data.msg);
    }
};
export const clearStoreThunk = async (message, thunkAPI) => {
    try {
        thunkAPI.dispatch(logoutUser(message));
        return Promise.resolve();
    } catch (error) {
        return Promise.reject();
    }
};
export const updateUserThunk = async (url, user, thunkAPI) => {
    try {
        const resp = await customFetch.put(`/auth/update-user/${thunkAPI.getState().user.user.id}`, user, {
            headers: {
                Authorization: `Bearer ${thunkAPI.getState().user.user.token}`,
            },
        });
        return resp.data;
    } catch (error) {
        if (error.response.status === 403) {
            thunkAPI.dispatch(logoutUser());
            return thunkAPI.rejectWithValue('Unauthorized! Logging Out...');
        }
        return thunkAPI.rejectWithValue(error.response.data.msg);
    }
};

export const updateUserProfilePictureThunk = async (url, formData, thunkAPI) => {
    try {
        const response = await customFetch.post(url, formData, {
            headers: {
                Authorization: `Bearer ${thunkAPI.getState().user.user.token}`,
                'Content-Type': 'multipart/form-data',
            },
        });
        window.location.reload();
        return response;
    } catch (error) {
        if (error.response.status === 403) {
            thunkAPI.dispatch(logoutUser());
            return thunkAPI.rejectWithValue('Unauthorized! Logging Out...');
        }
        return thunkAPI.rejectWithValue(error.response.data.msg);
    }
};
