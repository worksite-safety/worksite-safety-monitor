import React, { useState, useEffect } from 'react';
import './videoStream.css';
import { apiBaseUrl } from '../util/axios';

const VideoStream = () => {
    const [imageUrl, setImageUrl] = useState('');
    const [error, setError] = useState(false);
    const [myArray, setMyArray] = useState([]);

    const updateArray = (newItem) => {
        setMyArray((prevArray) => [...prevArray, newItem]);
    };

    useEffect(() => {
        const intervalId = setInterval(() => {
            // Loaded by the browser as an <img> src, not through axios, so it
            // needs the base URL directly. The timestamp is a cache-buster.
            const newImageUrl = `${apiBaseUrl}/event/get_image/${new Date().getTime()}`;
            updateArray(newImageUrl);
        }, 100);

        return () => clearInterval(intervalId);
    }, []);

    useEffect(() => {
        if (myArray.length > 15) {
            let index = 0;
            const intervalId = setInterval(() => {
                setImageUrl(myArray[index]);

                setMyArray((prevArray) => prevArray.slice(1));

                index = (index + 1) % myArray.length;
            }, 100); // every 0.1 seconds

            return () => clearInterval(intervalId);
        }
    }, [myArray]);

    const handleImageError = () => {
        setError(true);
    };

    return (
        <div className="video-stream-container">
            {error ? (
                <h1 className="error-message">Video Preview is Not Available</h1>
            ) : (
                <img src={imageUrl} alt="Output Image" />
            )}
        </div>
    );
};

export default VideoStream;
