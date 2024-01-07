import React, { useState, useEffect } from 'react';
import './videoStream.css'; // Import the CSS file
const VideoStream = () => {
    const [imageUrl, setImageUrl] = useState('');
    const [error, setError] = useState(false);
    const [myArray, setMyArray] = useState([]);

    // Function to update the array
    const updateArray = (newItem) => {
        // You can set the array using the setMyArray function
        setMyArray((prevArray) => [...prevArray, newItem]);
    };

    useEffect(() => {
        const intervalId = setInterval(() => {
            // Append a timestamp to the URL to ensure the image is not cached
            const newImageUrl = `http://localhost:5000/get_image?timestamp=${new Date().getTime()}`;
            updateArray(newImageUrl);
        }, 100); // Update every 0.1 seconds

        return () => clearInterval(intervalId); // Cleanup the interval on component unmount
    }, []);

    useEffect(() => {
        // Check if the array length is 100
        if (myArray.length > 15) {
            // Use an interval to iterate through the image URLs
            let index = 0;
            const intervalId = setInterval(() => {
                // Update the image URL
                setImageUrl(myArray[index]);

                // Remove the displayed image from the array
                setMyArray((prevArray) => prevArray.slice(1));

                // Move to the next image URL
                index = (index + 1) % myArray.length;
            }, 100); // Update every 0.1 seconds

            // Cleanup the interval on component unmount
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
