from threading import Thread
from queue import Queue
import grpc
from grpc import StatusCode
import os
import sys
from client.models.fileDetails import FileDetails
from client.db.dbOperations import GetUser, GetTokens, UpdateTokens

# Get the current directory
currentDir = os.path.dirname(os.path.realpath(__file__))
# append path of genproto to import following proto files
sys.path.append(currentDir + "/../genproto/")

import unitedShieldSpace_pb2 as ussPb
import unitedShieldSpace_pb2_grpc as unitedShieldSpace

serverAddress = "localhost"
serverPort = "7000"

chunkSize = 128


class UploadFile(Thread):
    def __init__(self, queue: Queue, filePath, *args, **kwargs):
        super().__init__(*args, *kwargs)
        self.queue = queue
        self.filePath = filePath
        print(filePath)
        self.fileName = os.path.basename(self.filePath)
        print(self.fileName)
        self.user = GetUser().get()
        (self.accessToken, self.refreshToken) = GetTokens().get()

    def run(self):
        channel = grpc.insecure_channel(serverAddress + ":" + serverPort)
        stub = unitedShieldSpace.UnitedShieldSpaceStub(channel)

        fileChunks = self.getFileChunks()
        try:
            # Trying to upload a file with saved tokens
            print("trying to upload with old tokens...")
            uploadResponse = stub.UploadFile(fileChunks)
            if uploadResponse.uploadStatus:
                self.queue.put(StatusCode.OK)
        except grpc.RpcError as rpcError:
            print("old tokens error - ", rpcError.code())
            # Access token was found invalid
            if rpcError.code() == StatusCode.UNAUTHENTICATED:
                try:
                    # try to get new tokens if refresh token is valid
                    print("trying to get new tokens...")
                    newTokensResponse = stub.GetNewTokens(
                        ussPb.RefreshTokenDetails(uid=self.user.userId, refreshToken=self.refreshToken))
                    print("new tokens :", newTokensResponse)
                    if UpdateTokens().update(newTokensResponse.accessToken, newTokensResponse.refreshToken):
                        self.accessToken = newTokensResponse.accessToken
                        self.refreshToken = newTokensResponse.refreshToken
                        fileChunks = self.getFileChunks()
                        try:
                            uploadResponse = stub.UploadFile(fileChunks)
                            if uploadResponse.uploadStatus:
                                self.queue.put(StatusCode.OK)
                        except grpc.RpcError as rpcError:
                            print("error when trying to send file with new tokens - ", rpcError.code())
                            self.queue.put(StatusCode.INTERNAL)
                except grpc.RpcError as rpcError:
                    # refresh token is invalid, return to login page
                    # means execute sign out logic...
                    print("refresh token is invalid...")
                    if rpcError.code() == StatusCode.UNAUTHENTICATED:
                        self.queue.put(StatusCode.UNAUTHENTICATED)
                    else:
                        self.queue.put(StatusCode.INTERNAL)
            else:
                self.queue.put(rpcError.code())

    def getFileChunks(self):
        with open(self.filePath, 'rb') as f:
            yield ussPb.FileSegment(email=self.user.email, uid=self.user.userId, fileName=self.fileName,
                                    accessToken=self.accessToken,
                                    fileSegmentData=None)
            while True:
                piece = f.read(chunkSize)
                if len(piece) == 0:
                    return
                yield ussPb.FileSegment(email=self.user.email, uid=self.user.userId, fileName=self.fileName,
                                        accessToken=self.accessToken,
                                        fileSegmentData=piece)


class GetUserFileList(Thread):
    def __init__(self, queue: Queue, uid, userEmail, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.queue = queue
        self.userEmail = userEmail
        self.uid = uid
        self.userFileResponse = None
        (self.accessToken, self.refreshToken) = GetTokens().get()
        self.fileDetailsArr = []

    def run(self):
        channel = grpc.insecure_channel(serverAddress + ":" + serverPort)
        stub = unitedShieldSpace.UnitedShieldSpaceStub(channel)
        try:
            print("trying to get user files with old tokens...")
            userFilesResponse = stub.ListUserFiles(
                ussPb.UserDetails(email=self.userEmail, accessToken=self.accessToken))
            for f in userFilesResponse:
                details = FileDetails(owner=self.userEmail, name=f.name, created=f.createdOn)
                self.fileDetailsArr.append(details)

            print(type(self.fileDetailsArr))
            self.queue.put(self.fileDetailsArr)

        except grpc.RpcError as rpcError:
            print("exception occured with old tokens...")
            print(rpcError.code())

            if rpcError.code() == StatusCode.UNAUTHENTICATED:
                print("invalid access token...")

                try:
                    print("trying to get new tokens...")
                    newTokensResponse = stub.GetNewTokens(
                        ussPb.RefreshTokenDetails(uid=self.uid, refreshToken=self.refreshToken))
                    print("new tokens :", newTokensResponse)
                    if UpdateTokens().update(newTokensResponse.accessToken, newTokensResponse.refreshToken):
                        self.accessToken = newTokensResponse.accessToken
                        self.refreshToken = newTokensResponse.refreshToken

                        try:
                            userFilesResponse = stub.ListUserFiles(
                                ussPb.UserDetails(email=self.userEmail, accessToken=self.accessToken))

                            for f in userFilesResponse:
                                details = FileDetails(owner=self.userEmail, name=f.name, created=f.createdOn)
                                self.fileDetailsArr.append(details)

                            print(self.fileDetailsArr)
                            self.queue.put(self.fileDetailsArr)
                        except grpc.RpcError as rpcError:
                            print("error occured with new tokens...")
                            print(rpcError.code())
                            self.queue.put(rpcError.code())
                    else:
                        self.queue.put(StatusCode.UNAUTHENTICATED)

                except grpc.RpcError as rpcError:
                    print("exception occured with ref token...")
                    print(rpcError.code())

                    if rpcError.code() == StatusCode.UNAUTHENTICATED:
                        print("invalid ref token, perform signout...")
                        self.queue.put(StatusCode.UNAUTHENTICATED)
                    else:
                        print("some other error occured while trying to get new tokens, perform signout...")
                        self.queue.put(rpcError.code())

            else:
                print("some other error occurred with old tokens...", rpcError.code())
                self.queue.put(rpcError.code())


class GetSharedWithMeFileList(Thread):
    def __init__(self, queue: Queue, uid, userEmail, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.queue = queue
        self.userEmail = userEmail
        self.uid = uid
        self.userFileResponse = None
        (self.accessToken, self.refreshToken) = GetTokens().get()
        self.fileDetailsArr = []

    def run(self):
        channel = grpc.insecure_channel(serverAddress + ":" + serverPort)
        stub = unitedShieldSpace.UnitedShieldSpaceStub(channel)
        try:
            print("trying to get user files with old tokens...")
            userFilesResponse = stub.ListSharedWithMeFiles(
                ussPb.UserDetails(email=self.userEmail, accessToken=self.accessToken))
            for f in userFilesResponse:
                details = FileDetails(owner=f.owner, name=f.name, created=f.createdOn)
                self.fileDetailsArr.append(details)

            print(type(self.fileDetailsArr))
            self.queue.put(self.fileDetailsArr)

        except grpc.RpcError as rpcError:
            print("exception occurred with old tokens...")
            print(rpcError.code())

            if rpcError.code() == StatusCode.UNAUTHENTICATED:
                print("invalid access token...")

                try:
                    print("trying to get new tokens...")
                    newTokensResponse = stub.GetNewTokens(
                        ussPb.RefreshTokenDetails(uid=self.uid, refreshToken=self.refreshToken))
                    print("new tokens :", newTokensResponse)
                    if UpdateTokens().update(newTokensResponse.accessToken, newTokensResponse.refreshToken):
                        self.accessToken = newTokensResponse.accessToken
                        self.refreshToken = newTokensResponse.refreshToken

                        try:
                            userFilesResponse = stub.ListSharedWithMeFiles(
                                ussPb.UserDetails(email=self.userEmail, accessToken=self.accessToken))

                            for f in userFilesResponse:
                                details = FileDetails(owner=f.owner, name=f.name, created=f.createdOn)
                                self.fileDetailsArr.append(details)

                            print(self.fileDetailsArr)
                            self.queue.put(self.fileDetailsArr)
                        except grpc.RpcError as rpcError:
                            print("error occured with new tokens...")
                            print(rpcError.code())
                            self.queue.put(rpcError.code())
                    else:
                        self.queue.put(StatusCode.UNAUTHENTICATED)

                except grpc.RpcError as rpcError:
                    print("exception occured with ref token...")
                    print(rpcError.code())

                    if rpcError.code() == StatusCode.UNAUTHENTICATED:
                        print("invalid ref token, perform signout...")
                        self.queue.put(StatusCode.UNAUTHENTICATED)
                    else:
                        print("some other error occured while trying to get new tokens, perform signout...")
                        self.queue.put(rpcError.code())

            else:
                print("some other error occurred with old tokens...", rpcError.code())
                self.queue.put(rpcError.code())


class UpdateFileACL(Thread):
    def __init__(self, queue: Queue, owner: str, name: str, grant: bool, toEmail: str, *args, **kwargs):
        super().__init__(*args, *kwargs)
        self.queue = queue
        self.owner = owner
        self.name = name
        self.toEmail = toEmail
        self.grant = grant
        self.user = GetUser.get()
        (self.accessToken, self.refreshToken) = GetTokens().get()

        self.ACLUpdateResponse = None

    def run(self):
        channel = grpc.insecure_channel(serverAddress + ":" + serverPort)
        stub = unitedShieldSpace.UnitedShieldSpaceStub(channel)
        try:
            print("trying to update ACL with old tokens...")
            self.ACLUpdateResponse = stub.UpdateACL(
                ussPb.ACLDetails(owner=self.owner, name=self.name, toEmail=self.toEmail, grant=self.grant,
                                 accessToken=self.accessToken))

            print(self.ACLUpdateResponse)
            if self.ACLUpdateResponse.ACLUpdateStatus:
                self.queue.put(StatusCode.OK)

        except grpc.RpcError as rpcError:
            print("exception occurred with old tokens...")
            print(rpcError.code())

            if rpcError.code() == StatusCode.UNAUTHENTICATED:
                print("invalid access token...")

                try:
                    print("trying to get new tokens...")
                    newTokensResponse = stub.GetNewTokens(
                        ussPb.RefreshTokenDetails(uid=self.user.userId, refreshToken=self.refreshToken))
                    print("new tokens :", newTokensResponse)
                    if UpdateTokens().update(newTokensResponse.accessToken, newTokensResponse.refreshToken):
                        self.accessToken = newTokensResponse.accessToken
                        self.refreshToken = newTokensResponse.refreshToken

                        try:

                            self.ACLUpdateResponse = stub.UpdateACL(
                                ussPb.ACLDetails(owner=self.owner, name=self.name, toEmail=self.toEmail,
                                                 grant=self.grant,
                                                 accessToken=self.accessToken))
                            print(self.ACLUpdateResponse)
                            if self.ACLUpdateResponse.ACLUpdateStatus:
                                self.queue.put(StatusCode.OK)

                        except grpc.RpcError as rpcError:
                            print("error occurred with new tokens...")
                            print(rpcError.code())
                            self.queue.put(rpcError.code())
                    else:
                        print("here unable to update tokens")
                        self.queue.put(StatusCode.UNAUTHENTICATED)

                except grpc.RpcError as rpcError:
                    print("exception occurred with ref token...")
                    print(rpcError.code())

                    if rpcError.code() == StatusCode.UNAUTHENTICATED:
                        print("invalid ref token, perform signout...")
                        self.queue.put(StatusCode.UNAUTHENTICATED)
                    else:
                        print("some other error occured while trying to get new tokens, perform signout...")
                        self.queue.put(rpcError.code())

            else:
                print("some other error occurred with old tokens...", rpcError.code())
                self.queue.put(rpcError.code())


class DownloadFile(Thread):
    def __init__(self, queue: Queue, owner: str, name: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.queue = queue
        self.owner = owner
        self.name = name

        self.fileTokenString = ""
        self.fileTokenResponse = None

        self.user = GetUser.get()
        (self.accessToken, self.refreshToken) = GetTokens().get()

    def run(self):
        print("run was called...")
        self.getFileToken()

    def getFileToken(self):
        channel = grpc.insecure_channel(serverAddress + ":" + serverPort)
        stub = unitedShieldSpace.UnitedShieldSpaceStub(channel)

        # get the file token
        try:
            print("trying to get the file token for download with old access tokens")

            self.fileTokenResponse = stub.GetFileToken(
                ussPb.FileTokenParams(accessToken=self.accessToken, owner=self.owner, name=self.name,
                                      requestor=self.user.email))
            print(self.fileTokenResponse)

            print("file token received")

            self.downloadFile()

        except grpc.RpcError as rpcError:
            print("error getting file token with old access token")
            print(rpcError.code())
            if rpcError.code() == StatusCode.UNAUTHENTICATED:
                print("invalid access token")

                try:
                    print("trying to get new tokens...")
                    newTokensResponse = stub.GetNewTokens(
                        ussPb.RefreshTokenDetails(uid=self.user.userId, refreshToken=self.refreshToken))
                    print("new tokens :", newTokensResponse)
                    if UpdateTokens().update(newTokensResponse.accessToken, newTokensResponse.refreshToken):
                        self.accessToken = newTokensResponse.accessToken
                        self.refreshToken = newTokensResponse.refreshToken

                        try:

                            self.fileTokenResponse = stub.GetFileToken(
                                ussPb.FileTokenParams(accessToken=self.accessToken, owner=self.owner, name=self.name,
                                                      requestor=self.user.email))
                            print(self.fileTokenResponse)

                            print("file token recieved")

                            self.downloadFile()

                        except grpc.RpcError as rpcError:
                            print("error occurred with new tokens...")
                            print(rpcError.code())
                            self.queue.put(rpcError.code())
                    else:
                        print("here unable to update tokens")
                        self.queue.put(StatusCode.UNAUTHENTICATED)

                except grpc.RpcError as rpcError:
                    print("exception occurred with ref token...")
                    print(rpcError.code())

                    if rpcError.code() == StatusCode.UNAUTHENTICATED:
                        print("invalid ref token, perform signout...")
                        self.queue.put(StatusCode.UNAUTHENTICATED)
                    else:
                        print("some other error occured while trying to get new tokens, perform signout...")
                        self.queue.put(rpcError.code())

            else:
                print(rpcError.code())
                print("unable to get new tokens - try again")

    def downloadFile(self):

        channel = grpc.insecure_channel(serverAddress + ":" + serverPort)
        stub = unitedShieldSpace.UnitedShieldSpaceStub(channel)

        try:
            downloadFileResponse = stub.DownloadFile(
                ussPb.RequestedFileDetails(accessToken=self.accessToken, fileToken=self.fileTokenResponse.fileToken,
                                           name=self.name, owner=self.owner, requestor=self.user.email))

            desktopPath = os.path.normpath(os.path.expanduser("~/Desktop"))

            print("file response - ", downloadFileResponse)

            with open(desktopPath + "/" + self.name, "wb") as file:
                for response in downloadFileResponse:
                    print(response)
                    file.write(response.fileSegmentData)

            self.queue.put(StatusCode.OK)

        except grpc.RpcError as rpcError:
            print(rpcError.code())
            self.queue.put(rpcError.code())
