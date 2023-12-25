import {toast} from "react-toastify";
import {createSlice, createAsyncThunk} from "@reduxjs/toolkit";
import customFetch from "../../util/axios";
import {addUserToLocalStorage, getUserFromLocalStorage, removeUserFromLocalStorage} from "../../util/localStorage";
import {
    clearStoreThunk,
    updateUserProfilePictureThunk,
    updateUserThunk,
} from './userThunk';


const initialState = {
    isLoading: false,
    isSidebarOpen: false,
    user: getUserFromLocalStorage(),
};
export const clearStore = createAsyncThunk('user/clearStore', clearStoreThunk);
export const registerUser = createAsyncThunk(
    'user/registerUser',
    async (user, thunkAPI) => {
        try {
            const resp = await customFetch.post('/auth/register ', user);
            return resp.data;
        } catch (error) {
            console.log(error)
            if (error.response.data.status === 400) {
                toast.error(JSON.stringify(error.response.data.errors))
            }
            if (error.response.status === 409) {
                toast.error(error.response.data.message)
            }
            return thunkAPI.rejectWithValue(error.response.data.msg);
        }
    })

export const loginUser = createAsyncThunk(
    'user/loginUser',
    async (user, thunkAPI) => {
        try {
            const resp = await customFetch.post('/auth/login', user);
            return resp.data;
        } catch (error) {
            return thunkAPI.rejectWithValue(error.response.data[0].message);
        }
    })
export const forgotPassword = createAsyncThunk(
    'user/forgot-password',
    async (email, thunkAPI) => {
        try {
            const resp = await customFetch.post('/auth/forgot-password ', email);
            toast.success("Password Change Mail Sent...")
            return resp.data;
        } catch (error) {
            if (error.response.status === 403) {

                toast.error("User Does Not Exists!!!")
            }
            return thunkAPI.rejectWithValue(error.response.data.msg);
        }
    })

export const changePassword = createAsyncThunk(
    'user/change-password',
    async (password, thunkAPI) => {
        console.log(password.email)

        try {
            const resp = await customFetch.put(`/auth/change-password/${password.email} `, password);
            toast.success("Password Changed Successfully...")
            return resp.data;
        } catch (error) {
            console.log(error)
            toast.error("Something Went Wrong!!!")

            return thunkAPI.rejectWithValue(error.response.data.msg);
        }
    });


export const updateUser = createAsyncThunk(
    'user/updateUser',
    async (user, thunkAPI) => {
        return updateUserThunk('/auth/edit', user, thunkAPI);
    }
);
export const updateUserProfilePicture = createAsyncThunk(
    'user/updateUserProfilePicture',
    async (formData, thunkAPI) => {
        const userId = thunkAPI.getState().user.user.id;
        try {
            const response = await updateUserProfilePictureThunk(
                `/auth/profile-image/${userId}`,
                formData,
                thunkAPI
            );
            return response.data;
        } catch (error) {
            if (error.response.status === 403) {
                thunkAPI.dispatch(logoutUser());
                return thunkAPI.rejectWithValue('Unauthorized! Logging Out...');
            }
            return thunkAPI.rejectWithValue(error.response.data.msg);
        }
    }
);


export const getAllJobsThunk = async (_, thunkAPI) => {


    let url = `/auth/getAllUsers`;
    try {
        const resp = await customFetch.get(url);
        return resp.data;
    } catch (error) {
        return thunkAPI.rejectWithValue(error.response.data.msg);
    }
};

const userSlice = createSlice({
    name: 'user',
    initialState,
    reducers: {
        toggleSidebar: (state) => {
            state.isSidebarOpen = !state.isSidebarOpen;
        },
        logoutUser: (state) => {
            state.user = null;
            state.isSidebarOpen = false;
            removeUserFromLocalStorage();
        },
    },
    extraReducers: {
        [registerUser.pending]: (state) => {
            state.isLoading = true;
        },
        [registerUser.fulfilled]: (state, {payload}) => {
            const {user} = payload;
            state.isLoading = false;
            state.user = user;
            addUserToLocalStorage(user);
            toast.success(`Hello There ${user.name}`);
        },
        [registerUser.rejected]: (state, {payload}) => {
            state.isLoading = false;
            toast.error(payload);
        },
        [loginUser.pending]: (state) => {
            state.isLoading = true;
        },
        [loginUser.fulfilled]: (state, {payload}) => {
            const {user} = payload;
            state.isLoading = false;
            state.user = user;
            addUserToLocalStorage(user);
            toast.success(`Hello There ${user.name}`);
        },
        [loginUser.rejected]: (state, {payload}) => {
            state.isLoading = false;
            toast.error(payload);
        },
        [updateUser.pending]: (state) => {
            state.isLoading = true;
        },
        [updateUser.fulfilled]: (state, {payload}) => {
            const {user} = payload;
            state.isLoading = false;
            state.user = user;

            addUserToLocalStorage(user);
            toast.success('User Updated');
        },
        [updateUser.rejected]: (state, {payload}) => {
            state.isLoading = false;
            toast.error(payload);
        }
    }

});
export const {toggleSidebar, logoutUser} = userSlice.actions;
export default userSlice.reducer;


